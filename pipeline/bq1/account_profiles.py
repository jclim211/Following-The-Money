#!/usr/bin/env python3
"""Build daily AML account behaviour profiles from cleaned transactions.

The job intentionally keeps the ground-truth ``is_laundering`` label out of
the behavioural profile. Labels are written to a separate Parquet dataset and
must only be joined during evaluation.

Expected input schema (clean transactions):
    ts, day, from_bank, from_account, from_country, to_bank, to_account,
    to_country, cross_border, crypto_involved, amount_paid,
    payment_currency, amount_received, receiving_currency, amount_usd,
    payment_format, is_laundering
"""

import argparse
import time
from datetime import datetime, timezone

from pyspark import StorageLevel
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F


DEFAULT_INPUT = "s3://is459-g7-projectbucket/clean/transactions/"
DEFAULT_PROFILES_OUTPUT = (
    "s3://is459-g7-projectbucket/curated/bq1/account_profiles/"
)
DEFAULT_LABELS_OUTPUT = "s3://is459-g7-projectbucket/curated/bq1/account_labels/"
DEFAULT_METRICS_OUTPUT = (
    "s3://is459-g7-projectbucket/metrics/bq1/account_profiles/"
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--profiles-output", default=DEFAULT_PROFILES_OUTPUT)
    parser.add_argument("--labels-output", default=DEFAULT_LABELS_OUTPUT)
    parser.add_argument("--metrics-output", default=DEFAULT_METRICS_OUTPUT)
    parser.add_argument(
        "--run-id",
        default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    )
    return parser.parse_args()


def clean_path(path):
    return path.rstrip("/")


def account_key(bank_column, account_column):
    """An account number is only unique when combined with its bank."""
    return F.concat_ws(":", bank_column, account_column)


def main():
    args = parse_args()
    started_at = datetime.now(timezone.utc)
    timer_start = time.perf_counter()

    spark = (
        SparkSession.builder.appName("IS459-BQ1-Account-Profiles")
        .getOrCreate()
    )
    spark.conf.set("spark.sql.adaptive.enabled", "true")
    spark.conf.set("spark.sql.parquet.compression.codec", "snappy")

    transactions = spark.read.parquet(clean_path(args.input))

    required_columns = {
        "ts",
        "day",
        "from_bank",
        "from_account",
        "to_bank",
        "to_account",
        "cross_border",
        "crypto_involved",
        "amount_usd",
        "payment_format",
        "is_laundering",
    }
    missing_columns = sorted(required_columns.difference(transactions.columns))
    if missing_columns:
        raise ValueError(f"Input is missing required columns: {missing_columns}")

    transactions = (
        transactions.select(*sorted(required_columns))
        .withColumn("profile_date", F.to_date("day"))
        .persist(StorageLevel.MEMORY_AND_DISK)
    )

    invalid_rows = transactions.filter(
        F.col("profile_date").isNull()
        | F.col("ts").isNull()
        | F.col("from_bank").isNull()
        | F.col("from_account").isNull()
        | F.col("to_bank").isNull()
        | F.col("to_account").isNull()
        | F.col("amount_usd").isNull()
        | (F.col("amount_usd") < 0)
        | F.col("is_laundering").isNull()
        | (~F.col("is_laundering").isin(0, 1))
    ).count()
    if invalid_rows:
        raise ValueError(
            f"Found {invalid_rows} rows with invalid keys, dates, amounts or labels"
        )

    input_rows = transactions.count()
    date_bounds = transactions.agg(
        F.min("profile_date").alias("first_date"),
        F.max("profile_date").alias("last_date"),
    ).first()
    first_date = date_bounds["first_date"]
    last_date = date_bounds["last_date"]

    # Calculate the daily amount band once from transactions, before creating
    # two account legs for every transfer. This avoids double-counting when
    # finding the daily median and 95th percentile.
    amount_bands = (
        transactions.groupBy("profile_date")
        .agg(
            F.percentile_approx("amount_usd", [0.50, 0.95], 10000).alias(
                "amount_percentiles"
            )
        )
        .select(
            "profile_date",
            F.col("amount_percentiles")[0].alias("daily_amount_p50_usd"),
            F.col("amount_percentiles")[1].alias("daily_amount_p95_usd"),
        )
    )

    # Every transfer becomes two account legs: one outgoing leg for the sender
    # and one incoming leg for the receiver.
    outgoing_legs = transactions.select(
        "profile_date",
        "ts",
        F.col("from_bank").alias("bank_id"),
        F.col("from_account").alias("account_id"),
        account_key(F.col("from_bank"), F.col("from_account")).alias(
            "account_key"
        ),
        account_key(F.col("to_bank"), F.col("to_account")).alias(
            "counterparty_key"
        ),
        F.lit("OUT").alias("direction"),
        "amount_usd",
        "payment_format",
        "cross_border",
        "crypto_involved",
    )

    incoming_legs = transactions.select(
        "profile_date",
        "ts",
        F.col("to_bank").alias("bank_id"),
        F.col("to_account").alias("account_id"),
        account_key(F.col("to_bank"), F.col("to_account")).alias(
            "account_key"
        ),
        account_key(F.col("from_bank"), F.col("from_account")).alias(
            "counterparty_key"
        ),
        F.lit("IN").alias("direction"),
        "amount_usd",
        "payment_format",
        "cross_border",
        "crypto_involved",
    )

    legs = outgoing_legs.unionByName(incoming_legs).persist(
        StorageLevel.MEMORY_AND_DISK
    )
    leg_rows = legs.count()
    if leg_rows != input_rows * 2:
        raise ValueError(
            f"Expected {input_rows * 2} account legs but produced {leg_rows}"
        )

    legs_with_bands = legs.join(amount_bands, "profile_date", "left")

    profiles = (
        legs_with_bands.groupBy(
            "profile_date", "bank_id", "account_id", "account_key"
        )
        .agg(
            F.count(F.lit(1)).alias("txn_count"),
            F.sum(F.when(F.col("direction") == "IN", 1).otherwise(0)).alias(
                "incoming_txn_count"
            ),
            F.sum(F.when(F.col("direction") == "OUT", 1).otherwise(0)).alias(
                "outgoing_txn_count"
            ),
            F.sum(
                F.when(F.col("direction") == "IN", F.col("amount_usd")).otherwise(
                    0.0
                )
            ).alias("incoming_amount_usd"),
            F.sum(
                F.when(
                    F.col("direction") == "OUT", F.col("amount_usd")
                ).otherwise(0.0)
            ).alias("outgoing_amount_usd"),
            F.sum("amount_usd").alias("total_amount_usd"),
            F.sum(
                F.when(F.col("payment_format") == "ACH", 1).otherwise(0)
            ).alias("ach_leg_count"),
            F.count("cross_border").alias("cross_border_eligible_count"),
            F.sum(F.when(F.col("cross_border") == F.lit(True), 1).otherwise(0)).alias(
                "cross_border_leg_count"
            ),
            F.sum(F.when(F.col("crypto_involved"), 1).otherwise(0)).alias(
                "crypto_leg_count"
            ),
            F.countDistinct(
                F.when(F.col("direction") == "IN", F.col("counterparty_key"))
            ).alias("fan_in"),
            F.countDistinct(
                F.when(F.col("direction") == "OUT", F.col("counterparty_key"))
            ).alias("fan_out"),
            F.first("daily_amount_p50_usd").alias("daily_amount_p50_usd"),
            F.first("daily_amount_p95_usd").alias("daily_amount_p95_usd"),
            F.sum(
                F.when(
                    (F.col("amount_usd") >= F.col("daily_amount_p50_usd"))
                    & (F.col("amount_usd") <= F.col("daily_amount_p95_usd")),
                    1,
                ).otherwise(0)
            ).alias("amount_band_leg_count"),
        )
        .withColumn("ach_share", F.col("ach_leg_count") / F.col("txn_count"))
        .withColumn(
            "cross_border_share",
            F.when(
                F.col("cross_border_eligible_count") > 0,
                F.col("cross_border_leg_count")
                / F.col("cross_border_eligible_count"),
            ).otherwise(F.lit(None).cast("double")),
        )
        .withColumn(
            "crypto_share", F.col("crypto_leg_count") / F.col("txn_count")
        )
        .withColumn(
            "amount_band_share",
            F.col("amount_band_leg_count") / F.col("txn_count"),
        )
    )

    # Scalable pass-through rule:
    # an outgoing leg is "fast" when the account had at least one incoming leg
    # at the same time or during the preceding 24 hours. The account-day value
    # is the share of outgoing USD value that meets this rule.
    event_window = (
        Window.partitionBy("account_key")
        .orderBy(F.col("event_epoch"))
        .rangeBetween(Window.unboundedPreceding, 0)
    )
    pass_through_daily = (
        legs.select(
            "profile_date",
            "account_key",
            "ts",
            "direction",
            "amount_usd",
        )
        .withColumn("event_epoch", F.col("ts").cast("long"))
        .withColumn(
            "last_incoming_epoch",
            F.max(
                F.when(F.col("direction") == "IN", F.col("event_epoch"))
            ).over(event_window),
        )
        .withColumn(
            "is_fast_outgoing",
            (F.col("direction") == "OUT")
            & F.col("last_incoming_epoch").isNotNull()
            & ((F.col("event_epoch") - F.col("last_incoming_epoch")) <= 86400),
        )
        .groupBy("profile_date", "account_key")
        .agg(
            F.sum(F.when(F.col("is_fast_outgoing"), 1).otherwise(0)).alias(
                "fast_outgoing_txn_count_24h"
            ),
            F.sum(
                F.when(F.col("is_fast_outgoing"), F.col("amount_usd")).otherwise(
                    0.0
                )
            ).alias("fast_outgoing_amount_usd_24h"),
        )
    )

    profiles = (
        profiles.join(
            pass_through_daily, ["profile_date", "account_key"], "left"
        )
        .fillna(
            {
                "fast_outgoing_txn_count_24h": 0,
                "fast_outgoing_amount_usd_24h": 0.0,
            }
        )
        .withColumn(
            "pass_through_share_24h_raw",
            F.when(
                F.col("outgoing_amount_usd") > 0,
                F.col("fast_outgoing_amount_usd_24h")
                / F.col("outgoing_amount_usd"),
            ).otherwise(F.lit(0.0)),
        )
        # The numerator and denominator are aggregated in separate Spark stages.
        # Floating-point addition can therefore produce values such as
        # 1.0000000000000002 when the mathematical result is exactly 1. Clamp
        # this subset share to its valid [0, 1] range before validation.
        .withColumn(
            "pass_through_share_24h",
            F.greatest(
                F.lit(0.0),
                F.least(F.lit(1.0), F.col("pass_through_share_24h_raw")),
            ),
        )
        .drop("pass_through_share_24h_raw")
    )

    # Compare today's activity with the preceding seven calendar days. Days
    # with no activity contribute zero. The first seven dataset days receive a
    # neutral ratio of 1.0 because a complete history is not yet available.
    activity_window = (
        Window.partitionBy("account_key")
        .orderBy(F.col("day_number"))
        .rangeBetween(-7, -1)
    )
    profiles = (
        profiles.withColumn(
            "day_number", F.datediff("profile_date", F.lit("1970-01-01"))
        )
        .withColumn(
            "trailing_7d_txn_count",
            F.coalesce(F.sum("txn_count").over(activity_window), F.lit(0)),
        )
        .withColumn(
            "trailing_7d_avg_txn_count", F.col("trailing_7d_txn_count") / 7.0
        )
        .withColumn(
            "activity_spike_ratio",
            F.when(
                F.datediff("profile_date", F.lit(str(first_date))) < 7,
                F.lit(1.0),
            ).otherwise(
                F.col("txn_count")
                / F.greatest(F.col("trailing_7d_avg_txn_count"), F.lit(1.0))
            ),
        )
        .drop("day_number", "trailing_7d_txn_count")
        .persist(StorageLevel.MEMORY_AND_DISK)
    )

    # Build labels in an entirely separate branch. The behavioural profile
    # above never reads or aggregates is_laundering.
    outgoing_labels = transactions.select(
        "profile_date",
        F.col("from_bank").alias("bank_id"),
        F.col("from_account").alias("account_id"),
        account_key(F.col("from_bank"), F.col("from_account")).alias(
            "account_key"
        ),
        "is_laundering",
    )
    incoming_labels = transactions.select(
        "profile_date",
        F.col("to_bank").alias("bank_id"),
        F.col("to_account").alias("account_id"),
        account_key(F.col("to_bank"), F.col("to_account")).alias(
            "account_key"
        ),
        "is_laundering",
    )
    labels = (
        outgoing_labels.unionByName(incoming_labels)
        .groupBy("profile_date", "bank_id", "account_id", "account_key")
        .agg(F.max("is_laundering").alias("account_day_is_laundering"))
        .persist(StorageLevel.MEMORY_AND_DISK)
    )

    profile_rows = profiles.count()
    label_rows = labels.count()
    if profile_rows != label_rows:
        raise ValueError(
            f"Profile/label row mismatch: profiles={profile_rows}, labels={label_rows}"
        )

    share_errors = profiles.filter(
        (F.col("ach_share") < 0)
        | (F.col("ach_share") > 1)
        | (
            F.col("cross_border_share").isNotNull()
            & (
                (F.col("cross_border_share") < 0)
                | (F.col("cross_border_share") > 1)
            )
        )
        | (F.col("crypto_share") < 0)
        | (F.col("crypto_share") > 1)
        | (F.col("amount_band_share") < 0)
        | (F.col("amount_band_share") > 1)
        | (F.col("pass_through_share_24h") < 0)
        | (F.col("pass_through_share_24h") > 1)
    ).count()
    if share_errors:
        raise ValueError(f"Found {share_errors} profiles with invalid share values")

    (
        profiles.repartition("profile_date")
        .write.mode("overwrite")
        .partitionBy("profile_date")
        .parquet(clean_path(args.profiles_output))
    )
    (
        labels.repartition("profile_date")
        .write.mode("overwrite")
        .partitionBy("profile_date")
        .parquet(clean_path(args.labels_output))
    )

    finished_at = datetime.now(timezone.utc)
    metrics = {
        "run_id": args.run_id,
        "status": "SUCCEEDED",
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "total_seconds": round(time.perf_counter() - timer_start, 3),
        "input_rows": input_rows,
        "account_leg_rows": leg_rows,
        "profile_rows": profile_rows,
        "label_rows": label_rows,
        "first_profile_date": str(first_date),
        "last_profile_date": str(last_date),
        "profiles_output": clean_path(args.profiles_output),
        "labels_output": clean_path(args.labels_output),
    }
    (
        spark.createDataFrame([metrics])
        .coalesce(1)
        .write.mode("overwrite")
        .json(f"{clean_path(args.metrics_output)}/run_id={args.run_id}")
    )

    profiles.unpersist()
    labels.unpersist()
    legs.unpersist()
    transactions.unpersist()
    spark.stop()


if __name__ == "__main__":
    main()
