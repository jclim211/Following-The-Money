"""Step 7: BQ2 analysis job, version 2. Runs after clean.py and schemes.py.

v2 changes the entry/exit rule (rule 3) and the expected counts (rule 4); v1 is bq2_analysis.py.

Reads clean/transactions, clean/schemes and clean/banks and writes six small tables:
  <curated>/flow_comparison/   laundering vs normal by payment_format, conversion, border
  <curated>/holding_time/      time from receiving money to sending money on, bucketed
  <curated>/scheme_profile/    one row per scheme: size, duration, USD, entry and exit bank
  <curated>/country_pairs/     from_country x to_country: laundering and normal flows
  <curated>/bank_entry_exit/   per bank: scheme entries and exits vs what its size predicts
  <curated>/scheme_edges/      one row per scheme transfer, account to account (network view)
  <metrics>/run=<ts>/          one JSON record for this run (row counts, checks, stage timings)

Rules:
  1. grp is laundering or normal (is_laundering). conversion = payment and receiving
     currency differ. border = crypto if a crypto bank is involved, else cross-border
     or domestic.
  2. Holding time: for each incoming transfer, the next outgoing transfer of the same
     account at or after the same minute. None before the data ends = never (this
     includes money received shortly before the last day).
  3. Entry accounts = accounts that only send inside a scheme (sources); exit accounts =
     accounts that only receive (sinks). Self-transfers are ignored for this. A scheme with
     no source (or no sink), e.g. a CYCLE, falls back to the sender of its earliest transfer
     (or the receiver of its latest; ties broken by step, tie counts in metrics).
     A bank's entries = schemes in which it holds at least one entry account; same for exits.
  4. Expected entries = all entries (sum over banks) x the bank's share of sent transactions;
     expected exits use all exits x its share of received transactions. Ratio = actual /
     expected, null when expected is 0. eligible = 5 or more actual.

Run on EMR Serverless (entry point):
  s3://<bucket>/scripts/bq2/bq2_analysis_v2.py
  arguments: --clean s3://<bucket>/clean --curated s3://<bucket>/curated/bq2
             --metrics s3://<bucket>/metrics/bq2/analysis --dataset HI-Medium
"""
import argparse
import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from pyspark import StorageLevel
from pyspark.sql import SparkSession, Window, functions as F

TX_COLS = ["ts", "from_bank", "from_account", "from_country", "to_bank", "to_account",
           "to_country", "cross_border", "crypto_involved", "payment_currency",
           "receiving_currency", "amount_usd", "payment_format", "is_laundering"]

DIMENSIONS = ["payment_format", "conversion", "border"]

ELIGIBLE_MIN = 5

# (upper bound in minutes, label); null hold time is "never"
BUCKETS = [(60, "<1h"), (360, "1-6h"), (1440, "6-24h"), (4320, "1-3d"), (None, ">3d")]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--clean", required=True, help="prefix holding transactions/, schemes/, banks/")
    p.add_argument("--curated", required=True, help="output prefix, e.g. s3://<bucket>/curated/bq2")
    p.add_argument("--metrics", required=True, help="metrics prefix, e.g. s3://<bucket>/metrics/bq2/analysis")
    p.add_argument("--dataset", default="HI-Medium")
    args = p.parse_args()
    clean, curated, metrics = args.clean.rstrip("/"), args.curated.rstrip("/"), args.metrics.rstrip("/")

    spark = SparkSession.builder.appName(f"aml-bq2-analysis-{args.dataset}").getOrCreate()
    spark.conf.set("spark.sql.session.timeZone", "UTC")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    m = {"dataset": args.dataset, "run_id": run_id, "job_version": "v2", "status": "running", "started_at": now_iso()}
    t_job = time.time()

    # Spark is lazy, so a stage's time is the time of the actions inside it.
    @contextmanager
    def stage(name):
        t = time.time()
        m[f"{name}_start"] = now_iso()
        yield
        m[f"{name}_end"] = now_iso()
        m[f"{name}_seconds"] = round(time.time() - t, 1)
        print(f"[bq2_analysis] {name}: {m[f'{name}_seconds']}s", flush=True)

    def write_metrics(status):
        m["status"] = status
        m["finished_at"] = now_iso()
        m["total_seconds"] = round(time.time() - t_job, 1)
        print("[bq2_analysis] metrics " + json.dumps(m), flush=True)
        (spark.createDataFrame([(json.dumps(m),)], "value string").coalesce(1)
         .write.mode("overwrite").text(f"{metrics}/run={run_id}/"))

    def write(df, name):
        df = df.cache()
        m[f"{name}_rows"] = df.count()
        df.coalesce(1).write.mode("overwrite").parquet(f"{curated}/{name}/")
        return df

    # ---- read: transactions once, with the derived columns, cached ------------------------------
    with stage("read"):
        tx = (spark.read.parquet(f"{clean}/transactions/").select(*TX_COLS)
              .withColumn("grp", F.when(F.col("is_laundering") == 1, F.lit("laundering"))
                                  .otherwise(F.lit("normal")))
              .withColumn("conversion", F.when(F.col("payment_currency") != F.col("receiving_currency"),
                                               F.lit("yes")).otherwise(F.lit("no")))
              .withColumn("border", F.when(F.col("crypto_involved"), F.lit("crypto"))
                                     .when(F.col("cross_border"), F.lit("cross-border"))
                                     .otherwise(F.lit("domestic")))
              .persist(StorageLevel.MEMORY_AND_DISK))
        c = tx.agg(F.count("*").alias("rows"), F.sum("is_laundering").alias("laundering")).first()
        m["tx_rows"], m["tx_laundering"] = c["rows"], c["laundering"]

        schemes = spark.read.parquet(f"{clean}/schemes/").cache()
        m["schemes"] = schemes.select("scheme_id").distinct().count()
        m["scheme_rows"] = schemes.count()

    # ---- 1. flow_comparison ---------------------------------------------------------------------
    with stage("flow_comparison"):
        parts = [tx.groupBy("grp", F.col(d).cast("string").alias("value"))
                   .agg(F.count("*").alias("n_tx"),
                        F.sum("amount_usd").alias("usd_total"),
                        F.percentile_approx("amount_usd", 0.5, 10000).alias("usd_median"))
                   .withColumn("dimension", F.lit(d))
                 for d in DIMENSIONS]
        flow = parts[0]
        for part in parts[1:]:
            flow = flow.unionByName(part)
        flow = (flow.withColumn("share", F.col("n_tx") / F.sum("n_tx").over(Window.partitionBy("dimension", "grp")))
                .select("dimension", "value", "grp", "n_tx", "share", "usd_total", "usd_median"))
        flow = write(flow, "flow_comparison")
        for r in flow.filter(F.col("grp") == "laundering").groupBy("dimension").agg(F.sum("n_tx")).collect():
            m[f"check_flow_laundering_{r[0]}"] = r[1]

    # ---- 2. holding_time ------------------------------------------------------------------------
    with stage("holding_time"):
        # kind 0 = money in, 1 = money out. Sorted newest first with out before in in the
        # same minute, the running min of out times is the next out at or after each in.
        ins = tx.select(F.col("to_bank").alias("bank"), F.col("to_account").alias("account"),
                        "ts", "grp", F.lit(0).alias("kind"))
        outs = tx.select(F.col("from_bank").alias("bank"), F.col("from_account").alias("account"),
                         "ts", F.lit(None).cast("string").alias("grp"), F.lit(1).alias("kind"))
        w = (Window.partitionBy("bank", "account")
             .orderBy(F.col("ts").desc(), F.col("kind").desc())
             .rowsBetween(Window.unboundedPreceding, Window.currentRow))
        held = (ins.unionByName(outs)
                .withColumn("next_out", F.min(F.when(F.col("kind") == 1, F.col("ts"))).over(w))
                .filter(F.col("kind") == 0)
                .withColumn("hold_minutes", ((F.unix_timestamp("next_out") - F.unix_timestamp("ts")) / 60)
                            .cast("long")))

        bucket = F.when(F.col("hold_minutes").isNull(), F.lit("never"))
        order = F.when(F.col("hold_minutes").isNull(), F.lit(len(BUCKETS) + 1))
        for i, (upper, label) in enumerate(BUCKETS, start=1):
            cond = F.col("hold_minutes") < upper if upper is not None else F.lit(True)
            bucket, order = bucket.when(cond, F.lit(label)), order.when(cond, F.lit(i))
        # Cached so the 58M-event sort runs once for both the buckets and the medians.
        held = (held.withColumn("bucket", bucket).withColumn("bucket_order", order)
                .select("grp", "hold_minutes", "bucket", "bucket_order")
                .persist(StorageLevel.MEMORY_AND_DISK))

        medians = held.groupBy("grp").agg(
            F.percentile_approx("hold_minutes", 0.5, 10000).alias("median_hold_minutes"))
        holding = (held.groupBy("grp", "bucket", "bucket_order").agg(F.count("*").alias("n"))
                   .withColumn("share", F.col("n") / F.sum("n").over(Window.partitionBy("grp")))
                   .join(medians, "grp", "left")
                   .select("grp", "bucket", "bucket_order", "n", "share", "median_hold_minutes"))
        holding = write(holding, "holding_time")
        m["check_holding_laundering"] = (holding.filter(F.col("grp") == "laundering")
                                         .agg(F.sum("n")).first()[0])
        held.unpersist()

    # ---- 4. country_pairs -----------------------------------------------------------------------
    with stage("country_pairs"):
        laund = F.col("is_laundering") == 1
        pairs = (tx.groupBy("from_country", "to_country")
                 .agg(F.sum(laund.cast("long")).alias("n_laundering"),
                      F.sum((~laund).cast("long")).alias("n_normal"),
                      F.sum(F.when(laund, F.col("amount_usd"))).alias("usd_laundering"),
                      F.sum(F.when(~laund, F.col("amount_usd"))).alias("usd_normal"))
                 .withColumn("laundering_rate",
                             F.col("n_laundering") / (F.col("n_laundering") + F.col("n_normal")))
                 .withColumn("share_of_laundering", F.col("n_laundering") / F.lit(m["tx_laundering"])))
        pairs = write(pairs, "country_pairs")
        m["check_country_pairs_laundering"] = pairs.agg(F.sum("n_laundering")).first()[0]

    # ---- 5. bank_entry_exit ---------------------------------------------------------------------
    with stage("bank_entry_exit"):
        first = Window.partitionBy("scheme_id").orderBy(F.col("ts").asc(), F.col("step").asc())
        last = Window.partitionBy("scheme_id").orderBy(F.col("ts").desc(), F.col("step").asc())
        ends = (schemes
                .withColumn("first_rank", F.row_number().over(first))
                .withColumn("last_rank", F.row_number().over(last)))
        entry = ends.filter(F.col("first_rank") == 1).select("scheme_id", F.col("from_bank").alias("entry_bank"))
        exit_ = ends.filter(F.col("last_rank") == 1).select("scheme_id", F.col("to_bank").alias("exit_bank"))
        scheme_ends = entry.join(exit_, "scheme_id").cache()

        # Ties: schemes with more than one bank in their first (or last) minute.
        bounds = schemes.groupBy("scheme_id").agg(F.min("ts").alias("first_ts"), F.max("ts").alias("last_ts"))
        b = schemes.join(bounds, "scheme_id")
        m["entry_ties"] = (b.filter(F.col("ts") == F.col("first_ts")).groupBy("scheme_id")
                           .agg(F.countDistinct("from_bank").alias("n")).filter(F.col("n") > 1).count())
        m["exit_ties"] = (b.filter(F.col("ts") == F.col("last_ts")).groupBy("scheme_id")
                          .agg(F.countDistinct("to_bank").alias("n")).filter(F.col("n") > 1).count())

        # Sources (only send) and sinks (only receive) per scheme, at account level.
        moves = schemes.filter(~F.col("is_self"))
        deg = (moves.select("scheme_id", F.col("from_bank").alias("bank_id"),
                            F.concat_ws(":", "from_bank", "from_account").alias("account"),
                            F.lit(1).alias("out_d"), F.lit(0).alias("in_d"))
               .unionByName(moves.select("scheme_id", F.col("to_bank").alias("bank_id"),
                                         F.concat_ws(":", "to_bank", "to_account").alias("account"),
                                         F.lit(0).alias("out_d"), F.lit(1).alias("in_d")))
               .groupBy("scheme_id", "bank_id", "account")
               .agg(F.sum("out_d").alias("out_deg"), F.sum("in_d").alias("in_deg")))
        src_banks = deg.filter((F.col("out_deg") > 0) & (F.col("in_deg") == 0)).select("scheme_id", "bank_id").distinct()
        snk_banks = deg.filter((F.col("in_deg") > 0) & (F.col("out_deg") == 0)).select("scheme_id", "bank_id").distinct()

        # Schemes without a source (or sink), e.g. cycles, fall back to the first sender (last receiver).
        all_ids = schemes.select("scheme_id").distinct()
        no_src = all_ids.join(src_banks.select("scheme_id").distinct(), "scheme_id", "left_anti")
        no_snk = all_ids.join(snk_banks.select("scheme_id").distinct(), "scheme_id", "left_anti")
        m["schemes_entry_fallback"] = no_src.count()
        m["schemes_exit_fallback"] = no_snk.count()
        entry_pairs = src_banks.unionByName(
            entry.join(no_src, "scheme_id").select("scheme_id", F.col("entry_bank").alias("bank_id"))).cache()
        exit_pairs = snk_banks.unionByName(
            exit_.join(no_snk, "scheme_id").select("scheme_id", F.col("exit_bank").alias("bank_id"))).cache()
        m["total_entries"] = entry_pairs.count()
        m["total_exits"] = exit_pairs.count()

        actual = (entry_pairs.groupBy("bank_id").agg(F.count("*").alias("entries"))
                  .join(exit_pairs.groupBy("bank_id").agg(F.count("*").alias("exits")), "bank_id", "full")
                  .fillna(0, ["entries", "exits"]))

        total = F.lit(m["tx_rows"])
        shares = (tx.groupBy(F.col("from_bank").alias("bank_id")).agg((F.count("*") / total).alias("sent_share"))
                  .join(tx.groupBy(F.col("to_bank").alias("bank_id")).agg((F.count("*") / total).alias("received_share")),
                        "bank_id", "full"))
        names = spark.read.parquet(f"{clean}/banks/").select("bank_id", "bank_name", "country")

        bee = (actual.join(shares, "bank_id", "left")
               .fillna(0.0, ["sent_share", "received_share"])
               .withColumn("expected_entries", F.lit(m["total_entries"]) * F.col("sent_share"))
               .withColumn("expected_exits", F.lit(m["total_exits"]) * F.col("received_share"))
               .withColumn("entry_ratio", F.when(F.col("expected_entries") > 0,
                                                 F.col("entries") / F.col("expected_entries")))
               .withColumn("exit_ratio", F.when(F.col("expected_exits") > 0,
                                                F.col("exits") / F.col("expected_exits")))
               .withColumn("entry_eligible", F.col("entries") >= ELIGIBLE_MIN)
               .withColumn("exit_eligible", F.col("exits") >= ELIGIBLE_MIN)
               .join(names, "bank_id", "left")
               .select("bank_id", "bank_name", "country", "entries", "exits", "sent_share", "received_share",
                       "expected_entries", "expected_exits", "entry_ratio", "exit_ratio",
                       "entry_eligible", "exit_eligible"))
        bee = write(bee, "bank_entry_exit")
        c = bee.agg(F.sum("entries").alias("entries"), F.sum("exits").alias("exits"),
                    F.sum(((F.col("entries") > 0) & (F.col("expected_entries") == 0)).cast("int")).alias("zero_in"),
                    F.sum(((F.col("exits") > 0) & (F.col("expected_exits") == 0)).cast("int")).alias("zero_out"),
                    F.sum(F.col("entry_eligible").cast("int")).alias("elig_in"),
                    F.sum(F.col("exit_eligible").cast("int")).alias("elig_out")).first()
        m.update({"check_entries_total": c["entries"], "check_exits_total": c["exits"],
                  "banks_zero_expected_entries": c["zero_in"], "banks_zero_expected_exits": c["zero_out"],
                  "banks_entry_eligible": c["elig_in"], "banks_exit_eligible": c["elig_out"]})
        tx.unpersist()

        # Entry and exit banks per scheme, as lists, for scheme_profile.
        scheme_lists = (entry_pairs.groupBy("scheme_id")
                        .agg(F.count("*").alias("n_entry_banks"),
                             F.concat_ws(",", F.sort_array(F.collect_list("bank_id"))).alias("entry_banks"))
                        .join(exit_pairs.groupBy("scheme_id")
                              .agg(F.count("*").alias("n_exit_banks"),
                                   F.concat_ws(",", F.sort_array(F.collect_list("bank_id"))).alias("exit_banks")),
                              "scheme_id", "full"))

    # ---- 3. scheme_profile ----------------------------------------------------------------------
    with stage("scheme_profile"):
        sides = (schemes.select("scheme_id", F.concat_ws(":", "from_bank", "from_account").alias("account"),
                                F.col("from_bank").alias("bank"), F.col("from_country").alias("country"))
                 .unionByName(schemes.select("scheme_id", F.concat_ws(":", "to_bank", "to_account").alias("account"),
                                             F.col("to_bank").alias("bank"), F.col("to_country").alias("country")))
                 .groupBy("scheme_id")
                 .agg(F.countDistinct("account").alias("n_accounts"),
                      F.countDistinct("bank").alias("n_banks"),
                      F.countDistinct("country").alias("n_countries")))
        profile = (schemes.groupBy("scheme_id", "scheme_type")
                   .agg(F.count("*").alias("n_transfers"),
                        F.min("ts").alias("start_ts"), F.max("ts").alias("end_ts"),
                        F.sum("amount_usd").alias("total_usd"),
                        F.avg(F.col("in_clean").cast("double")).alias("share_in_clean"))
                   .withColumn("duration_hours",
                               (F.unix_timestamp("end_ts") - F.unix_timestamp("start_ts")) / 3600)
                   .join(sides, "scheme_id")
                   .join(scheme_ends, "scheme_id", "left")
                   .join(scheme_lists, "scheme_id", "left")
                   # entry_bank / exit_bank = first sender / last receiver; entry_banks / exit_banks = all
                   # banks holding a source / sink account (comma-separated bank ids).
                   .select("scheme_id", "scheme_type", "n_transfers", "n_accounts", "n_banks", "n_countries",
                           "start_ts", "end_ts", "duration_hours", "total_usd", "share_in_clean",
                           "entry_bank", "exit_bank", "n_entry_banks", "entry_banks", "n_exit_banks",
                           "exit_banks"))
        write(profile, "scheme_profile")

    # ---- 6. scheme_edges ------------------------------------------------------------------------
    with stage("scheme_edges"):
        edges = schemes.select("scheme_id", "scheme_type", "step", "ts",
                               F.concat_ws(":", "from_bank", "from_account").alias("src"),
                               F.concat_ws(":", "to_bank", "to_account").alias("dst"),
                               "from_bank", "to_bank", "from_country", "to_country",
                               "amount_usd", "payment_format")
        write(edges, "scheme_edges")

    write_metrics("succeeded")
    spark.stop()


if __name__ == "__main__":
    main()
