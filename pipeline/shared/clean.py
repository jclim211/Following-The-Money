"""Step 4: shared cleaning job (used by both BQ1 and BQ2).

Reads the raw IBM AML files and writes:
  <clean>/transactions/   cleaned transactions, Parquet, partitioned by day
  <clean>/banks/          one row per bank: id, name, country, flags, total traffic
  <clean>/fx_rates/       currency -> units per USD, derived from the data
  <metrics>/run=<ts>/     one JSON record for this run (row counts, stage timings)

Cleaning rules:
  1. Strip leading zeros from bank IDs so they join accounts.csv
  2. Drop exact duplicate rows
  3. Fail the job if any timestamp does not parse (profiling found none)
  4. Drop transfers from an account to itself
  5. Cut the laundering-heavy tail: keep days up to the last day whose volume
     is above --tail-fraction of the median daily volume
  6. Convert amounts to USD with the exchange rates implied in the data
  7. Country from the bank name "<Country> Bank #n". Names without that prefix are
     US-style ("First Bank of Helena") and set to US with country_inferred = true.
     The dataset's "Crytpo" banks become "Crypto".
  8. cross_border is NULL when either side is a crypto bank (a crypto bank is not a
     jurisdiction); crypto_involved flags those rows instead.

Run on EMR Serverless (entry point):
  s3://<bucket>/scripts/shared/clean.py
  arguments: --raw s3://<bucket>/raw --clean s3://<bucket>/clean
             --metrics s3://<bucket>/metrics/clean --dataset HI-Medium
"""
import argparse
import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from pyspark import StorageLevel
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import StructType, StructField, StringType

RAW_COLS = ["ts", "from_bank", "from_account", "to_bank", "to_account",
            "amount_received", "receiving_currency", "amount_paid",
            "payment_currency", "payment_format", "is_laundering"]

CLEAN_COLS = ["ts", "day", "from_bank", "from_account", "from_country",
              "to_bank", "to_account", "to_country", "cross_border", "crypto_involved",
              "amount_paid", "payment_currency", "amount_received", "receiving_currency",
              "amount_usd", "payment_format", "is_laundering"]


def strip_zeros(col):
    stripped = F.regexp_replace(col, "^0+", "")
    return F.when(stripped == "", F.lit("0")).otherwise(stripped)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", required=True, help="prefix holding transactions/ and accounts/")
    p.add_argument("--clean", required=True, help="output prefix")
    p.add_argument("--metrics", required=True, help="metrics prefix, e.g. s3://<bucket>/metrics/clean")
    p.add_argument("--dataset", default="HI-Medium")
    p.add_argument("--tail-fraction", type=float, default=0.10)
    args = p.parse_args()
    raw, clean, metrics = args.raw.rstrip("/"), args.clean.rstrip("/"), args.metrics.rstrip("/")

    spark = SparkSession.builder.appName(f"aml-clean-{args.dataset}").getOrCreate()
    spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    m = {"dataset": args.dataset, "run_id": run_id, "status": "running",
         "started_at": now_iso(), "tail_fraction": args.tail_fraction}
    t_job = time.time()

    # Spark is lazy, so a stage's time is the time of the actions inside it.
    @contextmanager
    def stage(name):
        t = time.time()
        m[f"{name}_start"] = now_iso()
        yield
        m[f"{name}_end"] = now_iso()
        m[f"{name}_seconds"] = round(time.time() - t, 1)
        print(f"[clean] {name}: {m[f'{name}_seconds']}s", flush=True)

    def write_metrics(status):
        m["status"] = status
        m["finished_at"] = now_iso()
        m["total_seconds"] = round(time.time() - t_job, 1)
        print("[clean] metrics " + json.dumps(m), flush=True)
        (spark.createDataFrame([(json.dumps(m),)], "value string").coalesce(1)
         .write.mode("overwrite").text(f"{metrics}/run={run_id}/"))

    # ---- read + dedup: the only full pass over the CSV --------------------------------------
    with stage("read"):
        # The header repeats "Account", so apply our own column names and skip it.
        schema = StructType([StructField(c, StringType()) for c in RAW_COLS])
        raw_tx = spark.read.csv(f"{raw}/transactions/", header=True, schema=schema)

        # groupBy all columns = dedup, and the per-group count gives the raw row count too.
        parsed = (raw_tx.groupBy(*RAW_COLS).agg(F.count("*").alias("n_copies"))
                  .withColumn("ts_raw", F.col("ts"))
                  .withColumn("ts", F.to_timestamp("ts", "yyyy/MM/dd HH:mm"))
                  .withColumn("day", F.to_date("ts"))
                  .withColumn("from_bank", strip_zeros("from_bank"))
                  .withColumn("to_bank", strip_zeros("to_bank"))
                  .withColumn("amount_paid", F.col("amount_paid").cast("double"))
                  .withColumn("amount_received", F.col("amount_received").cast("double"))
                  .withColumn("is_laundering", F.col("is_laundering").cast("int"))
                  .withColumn("is_self", (F.col("from_bank") == F.col("to_bank")) &
                                         (F.col("from_account") == F.col("to_account")))
                  .persist(StorageLevel.MEMORY_AND_DISK))

        c = parsed.agg(F.sum("n_copies").alias("raw"), F.count("*").alias("dedup"),
                       F.sum(F.col("ts").isNull().cast("int")).alias("bad_ts"),
                       F.sum(F.col("is_self").cast("int")).alias("self")).first()
        m["raw_rows"], m["dedup_rows"] = c["raw"], c["dedup"]
        m["duplicates_dropped"] = c["raw"] - c["dedup"]
        m["bad_timestamp_rows"] = c["bad_ts"]
        m["self_transfers_dropped"] = c["self"]

    if m["bad_timestamp_rows"] > 0:
        bad = [r["ts_raw"] for r in parsed.filter(F.col("ts").isNull()).select("ts_raw").limit(5).collect()]
        m["bad_timestamp_examples"] = bad
        write_metrics("failed_bad_timestamps")
        spark.stop()
        raise RuntimeError(f"{m['bad_timestamp_rows']} timestamps did not parse, e.g. {bad}")

    # ---- clean: self-transfers, tail cutoff, fx (all from the cached copy) -------------------
    with stage("clean"):
        tx = parsed.filter(~F.col("is_self"))

        daily = tx.groupBy("day").count()
        median_daily = daily.agg(F.percentile_approx("count", 0.5)).first()[0]
        cutoff = (daily.filter(F.col("count") > args.tail_fraction * median_daily)
                  .agg(F.max("day")).first()[0])
        m["median_daily_rows"] = median_daily
        m["cutoff_day"] = str(cutoff)
        m["tail_rows_dropped"] = tx.filter(F.col("day") > F.lit(cutoff)).count()
        tx = tx.filter(F.col("day") <= F.lit(cutoff))

        # Exchange rates implied by conversions to or from USD, in both directions.
        # Built from parsed (before the self-transfer filter): 98% of conversions are self-transfers.
        # units of currency per USD, median per currency
        usd = F.lit("US Dollar")
        paid_x = (parsed.filter((F.col("receiving_currency") == usd) & (F.col("payment_currency") != usd))
                  .select(F.col("payment_currency").alias("currency"),
                          (F.col("amount_paid") / F.col("amount_received")).alias("rate")))
        recv_x = (parsed.filter((F.col("payment_currency") == usd) & (F.col("receiving_currency") != usd))
                  .select(F.col("receiving_currency").alias("currency"),
                          (F.col("amount_received") / F.col("amount_paid")).alias("rate")))
        fx = (paid_x.unionByName(recv_x)
              .groupBy("currency")
              .agg(F.percentile_approx("rate", 0.5, 100000).alias("units_per_usd"),
                   F.count("*").alias("n_obs"))
              .unionByName(spark.createDataFrame([("US Dollar", 1.0, 0)],
                                                 "currency string, units_per_usd double, n_obs long"))
              .cache())
        m["fx_currencies"] = fx.count()

        # Banks: name and country from accounts.csv
        acc = spark.read.csv(f"{raw}/accounts/", header=True)
        prefix = F.regexp_extract("bank_name", r"^(.*) Bank #", 1)
        names = (acc.select(strip_zeros(F.col("Bank ID")).alias("bank_id"),
                            F.col("Bank Name").alias("bank_name"))
                 .dropDuplicates(["bank_id"])
                 .withColumn("country_inferred", prefix == "")
                 .withColumn("country", F.when(prefix == "", F.lit("US"))
                                         .when(prefix == "Crytpo", F.lit("Crypto"))
                                         .otherwise(prefix))
                 .withColumn("is_crypto_bank", F.col("country") == "Crypto")
                 .cache())

    # ---- write transactions --------------------------------------------------------------------
    with stage("write_transactions"):
        side = names.select("bank_id", "country", "is_crypto_bank")
        from_side = F.broadcast(side.select(F.col("bank_id").alias("from_bank"),
                                            F.col("country").alias("from_country"),
                                            F.col("is_crypto_bank").alias("from_crypto")))
        to_side = F.broadcast(side.select(F.col("bank_id").alias("to_bank"),
                                          F.col("country").alias("to_country"),
                                          F.col("is_crypto_bank").alias("to_crypto")))
        crypto = F.coalesce(F.col("from_crypto"), F.lit(False)) | F.coalesce(F.col("to_crypto"), F.lit(False))

        tx = (tx.join(F.broadcast(fx.select(F.col("currency").alias("payment_currency"),
                                            "units_per_usd")), "payment_currency", "left")
              .withColumn("amount_usd", F.col("amount_paid") / F.col("units_per_usd"))
              .join(from_side, "from_bank", "left")
              .join(to_side, "to_bank", "left")
              .withColumn("crypto_involved", crypto)
              .withColumn("cross_border", F.when(crypto, F.lit(None).cast("boolean"))
                                           .otherwise(F.col("from_country") != F.col("to_country")))
              .select(*CLEAN_COLS)
              .persist(StorageLevel.MEMORY_AND_DISK))

        (tx.repartition("day").write.mode("overwrite").partitionBy("day")
           .parquet(f"{clean}/transactions/"))
        parsed.unpersist()

    # ---- write banks and fx ------------------------------------------------------------------
    with stage("write_banks"):
        touches = (tx.select(F.col("from_bank").alias("bank_id"))
                   .unionByName(tx.filter(F.col("to_bank") != F.col("from_bank"))
                                .select(F.col("to_bank").alias("bank_id"))))
        traffic = touches.groupBy("bank_id").agg(F.count("*").alias("total_txns"))
        banks = traffic.join(names, "bank_id", "left").cache()
        banks.coalesce(1).write.mode("overwrite").parquet(f"{clean}/banks/")
        fx.coalesce(1).write.mode("overwrite").parquet(f"{clean}/fx_rates/")

    # ---- summary -----------------------------------------------------------------------------
    s = tx.agg(F.count("*").alias("rows"), F.sum("is_laundering").alias("laundering"),
               F.min("day").alias("first_day"), F.max("day").alias("last_day"),
               F.sum(F.col("amount_usd").isNull().cast("int")).alias("no_usd"),
               F.sum((F.col("from_country").isNull() |
                      F.col("to_country").isNull()).cast("int")).alias("no_country"),
               F.sum(F.col("crypto_involved").cast("int")).alias("crypto"),
               F.sum(F.col("cross_border").cast("int")).alias("cross_border")).first()
    m.update({"clean_rows": s["rows"], "clean_laundering": s["laundering"],
              "first_day": str(s["first_day"]), "last_day": str(s["last_day"]),
              "rows_without_usd": s["no_usd"], "rows_without_country": s["no_country"],
              "crypto_rows": s["crypto"], "cross_border_rows": s["cross_border"],
              "banks": banks.count(),
              "banks_country_inferred": banks.filter(F.col("country_inferred")).count()})

    write_metrics("succeeded")
    spark.stop()


if __name__ == "__main__":
    main()
