"""Step 6: BQ2 schemes job. Runs after clean.py.

Parses Patterns.txt into one row per scheme transfer and writes:
  <clean>/schemes/        Parquet, one row per transfer, with scheme_id and scheme_type
  <metrics>/run=<ts>/     one JSON record for this run (row counts, match rate, stage timings)

Rules:
  1. Each "BEGIN LAUNDERING ATTEMPT - <TYPE>[: <detail>]" line starts a new scheme_id
     (numbered in file order); the lines until "END ..." are its transfers.
  2. Types are cast exactly as in clean.py (bank IDs without leading zeros).
  3. Country, cross_border, crypto_involved and amount_usd use clean/banks and
     clean/fx_rates, so the US and crypto rules match the clean transactions.
  4. Each transfer is matched to the clean transactions on ts, both banks, both
     accounts, amount_paid, payment_currency and payment_format (in_clean flag).
  5. Transfers after the clean cutoff day are kept: schemes often finish after it, and
     a scheme's exit bank is its last transfer.
  6. step is the order inside the file block, which is not always chronological.
     Use ts to find a scheme's first (entry) and last (exit) transfer.

Run on EMR Serverless (entry point):
  s3://<bucket>/scripts/bq2/schemes.py
  arguments: --raw s3://<bucket>/raw --clean s3://<bucket>/clean
             --metrics s3://<bucket>/metrics/schemes --dataset HI-Medium
"""
import argparse
import json
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from pyspark.sql import SparkSession, functions as F

PATTERN_COLS = ["ts", "from_bank", "from_account", "to_bank", "to_account",
                "amount_received", "receiving_currency", "amount_paid",
                "payment_currency", "payment_format", "is_laundering"]

MATCH_KEY = ["ts", "from_bank", "from_account", "to_bank", "to_account",
             "amount_paid", "payment_currency", "payment_format"]

SCHEME_COLS = ["scheme_id", "scheme_type", "scheme_detail", "step", "ts", "day",
               "from_bank", "from_account", "from_country", "to_bank", "to_account", "to_country",
               "cross_border", "crypto_involved", "amount_paid", "payment_currency",
               "amount_received", "receiving_currency", "amount_usd", "payment_format",
               "is_self", "in_clean"]

BEGIN = re.compile(r"^BEGIN LAUNDERING ATTEMPT - ([^:]+?)\s*(?::\s*(.*))?$")


def strip_zeros(col):
    stripped = F.regexp_replace(col, "^0+", "")
    return F.when(stripped == "", F.lit("0")).otherwise(stripped)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_patterns(text):
    """One tuple per transfer: (scheme_id, scheme_type, scheme_detail, step, *11 raw fields)."""
    rows, scheme_id, scheme_type, detail, step = [], 0, None, None, 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = BEGIN.match(line)
        if m:
            scheme_id += 1
            scheme_type, detail, step = m.group(1).strip(), (m.group(2) or "").strip() or None, 0
            continue
        if line.startswith("END LAUNDERING ATTEMPT"):
            scheme_type = None
            continue
        parts = line.split(",")
        if scheme_type is None or len(parts) != len(PATTERN_COLS):
            raise ValueError(f"Unexpected line in Patterns.txt: {line[:120]}")
        step += 1
        rows.append((scheme_id, scheme_type, detail, step, *parts))
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", required=True, help="prefix holding patterns/")
    p.add_argument("--clean", required=True, help="prefix holding transactions/, banks/, fx_rates/")
    p.add_argument("--metrics", required=True, help="metrics prefix, e.g. s3://<bucket>/metrics/schemes")
    p.add_argument("--dataset", default="HI-Medium")
    args = p.parse_args()
    raw, clean, metrics = args.raw.rstrip("/"), args.clean.rstrip("/"), args.metrics.rstrip("/")

    spark = SparkSession.builder.appName(f"aml-schemes-{args.dataset}").getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    m = {"dataset": args.dataset, "run_id": run_id, "status": "running", "started_at": now_iso()}
    t_job = time.time()

    # Spark is lazy, so a stage's time is the time of the actions inside it.
    @contextmanager
    def stage(name):
        t = time.time()
        m[f"{name}_start"] = now_iso()
        yield
        m[f"{name}_end"] = now_iso()
        m[f"{name}_seconds"] = round(time.time() - t, 1)
        print(f"[schemes] {name}: {m[f'{name}_seconds']}s", flush=True)

    def write_metrics(status):
        m["status"] = status
        m["finished_at"] = now_iso()
        m["total_seconds"] = round(time.time() - t_job, 1)
        print("[schemes] metrics " + json.dumps(m), flush=True)
        (spark.createDataFrame([(json.dumps(m),)], "value string").coalesce(1)
         .write.mode("overwrite").text(f"{metrics}/run={run_id}/"))

    # ---- read + parse: the file is a few MB, so it is parsed on the driver -------------------
    with stage("parse"):
        files = spark.read.text(f"{raw}/patterns/", wholetext=True).collect()
        rows = [r for f in files for r in parse_patterns(f["value"])]
        schema = ("scheme_id int, scheme_type string, scheme_detail string, step int, "
                  + ", ".join(f"{c} string" for c in PATTERN_COLS))
        pat = (spark.createDataFrame(rows, schema)
               .withColumn("ts_raw", F.col("ts"))
               .withColumn("ts", F.to_timestamp("ts", "yyyy/MM/dd HH:mm"))
               .withColumn("day", F.to_date("ts"))
               .withColumn("from_bank", strip_zeros("from_bank"))
               .withColumn("to_bank", strip_zeros("to_bank"))
               .withColumn("amount_paid", F.col("amount_paid").cast("double"))
               .withColumn("amount_received", F.col("amount_received").cast("double"))
               .withColumn("is_self", (F.col("from_bank") == F.col("to_bank")) &
                                      (F.col("from_account") == F.col("to_account")))
               .cache())
        m["schemes"] = pat.select("scheme_id").distinct().count()
        m["scheme_rows"] = pat.count()
        m["bad_timestamp_rows"] = pat.filter(F.col("ts").isNull()).count()

    if m["bad_timestamp_rows"] > 0:
        bad = [r["ts_raw"] for r in pat.filter(F.col("ts").isNull()).select("ts_raw").limit(5).collect()]
        m["bad_timestamp_examples"] = bad
        write_metrics("failed_bad_timestamps")
        spark.stop()
        raise RuntimeError(f"{m['bad_timestamp_rows']} timestamps did not parse, e.g. {bad}")

    # ---- enrich and match against the clean tables -------------------------------------------
    with stage("enrich_match"):
        banks = spark.read.parquet(f"{clean}/banks/").select("bank_id", "country", "is_crypto_bank")
        fx = spark.read.parquet(f"{clean}/fx_rates/").select(
            F.col("currency").alias("payment_currency"), "units_per_usd")
        from_side = F.broadcast(banks.select(F.col("bank_id").alias("from_bank"),
                                             F.col("country").alias("from_country"),
                                             F.col("is_crypto_bank").alias("from_crypto")))
        to_side = F.broadcast(banks.select(F.col("bank_id").alias("to_bank"),
                                           F.col("country").alias("to_country"),
                                           F.col("is_crypto_bank").alias("to_crypto")))
        crypto = F.coalesce(F.col("from_crypto"), F.lit(False)) | F.coalesce(F.col("to_crypto"), F.lit(False))

        # Only the key columns of the clean transactions are read; the pattern rows are tiny.
        clean_tx = spark.read.parquet(f"{clean}/transactions/")
        window = clean_tx.agg(F.min("day").alias("first"), F.max("day").alias("last")).first()
        m["clean_first_day"], m["clean_last_day"] = str(window["first"]), str(window["last"])
        matched = (clean_tx.select(*MATCH_KEY)
                   .join(F.broadcast(pat.select(*MATCH_KEY).distinct()), MATCH_KEY, "inner")
                   .distinct()
                   .withColumn("in_clean", F.lit(True)))

        schemes = (pat
                   .join(F.broadcast(fx), "payment_currency", "left")
                   .withColumn("amount_usd", F.col("amount_paid") / F.col("units_per_usd"))
                   .join(from_side, "from_bank", "left")
                   .join(to_side, "to_bank", "left")
                   .withColumn("crypto_involved", crypto)
                   .withColumn("cross_border", F.when(crypto, F.lit(None).cast("boolean"))
                                                .otherwise(F.col("from_country") != F.col("to_country")))
                   .join(matched, MATCH_KEY, "left")
                   .withColumn("in_clean", F.coalesce(F.col("in_clean"), F.lit(False)))
                   .select(*SCHEME_COLS)
                   .cache())

        in_window = F.col("day").between(F.lit(window["first"]), F.lit(window["last"]))
        s = schemes.agg(
            F.sum(F.col("in_clean").cast("int")).alias("matched"),
            F.sum((F.col("is_self")).cast("int")).alias("self"),
            F.sum((in_window & ~F.col("in_clean") & ~F.col("is_self")).cast("int")).alias("unmatched"),
            F.sum((F.col("day") > F.lit(window["last"])).cast("int")).alias("tail"),
            F.sum(F.col("amount_usd").isNull().cast("int")).alias("no_usd"),
            F.sum((F.col("from_country").isNull() |
                   F.col("to_country").isNull()).cast("int")).alias("no_country"),
            F.sum(F.col("crypto_involved").cast("int")).alias("crypto"),
            F.min("day").alias("first_day"), F.max("day").alias("last_day")).first()
        m.update({"matched_to_clean_rows": s["matched"],
                  "self_transfer_rows": s["self"],
                  "unmatched_in_window_rows": s["unmatched"],
                  "after_cutoff_rows": s["tail"],
                  "rows_without_usd": s["no_usd"],
                  "rows_without_country": s["no_country"],
                  "crypto_rows": s["crypto"],
                  "first_day": str(s["first_day"]), "last_day": str(s["last_day"])})
        # Flat keys (schemes_fan_out, ...) so the metrics crawler makes plain columns.
        for r in schemes.groupBy("scheme_type").agg(F.countDistinct("scheme_id").alias("n")).collect():
            m["schemes_" + re.sub(r"[^a-z0-9]+", "_", r["scheme_type"].lower())] = r["n"]

    # ---- write -----------------------------------------------------------------------------
    with stage("write_schemes"):
        schemes.coalesce(1).write.mode("overwrite").parquet(f"{clean}/schemes/")

    write_metrics("succeeded")
    spark.stop()


if __name__ == "__main__":
    main()
