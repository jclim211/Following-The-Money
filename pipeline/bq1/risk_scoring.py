#!/usr/bin/env python3
"""Score and rank daily AML account profiles, then evaluate review capacities.

The risk score is built only from behavioural profile fields. The ground-truth
``account_day_is_laundering`` label is kept separate until after all scores and
ranks are fixed, so the answer is not leaked into the model.

Default outputs:
  * risk_rankings: one scored/ranked row per account and day (no label)
  * capacity_evaluation: daily results for each investigator capacity
  * capacity_summary: overall results and a practical score threshold
  * metrics: run metadata and validation counts
"""

import argparse
import time
from datetime import datetime, timezone

from pyspark import StorageLevel
from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F


DEFAULT_PROFILES_INPUT = (
    "s3://is459-g7-projectbucket/curated/bq1/account_profiles/"
)
DEFAULT_LABELS_INPUT = (
    "s3://is459-g7-projectbucket/curated/bq1/account_labels/"
)
DEFAULT_RANKINGS_OUTPUT = (
    "s3://is459-g7-projectbucket/curated/bq1/risk_rankings/"
)
DEFAULT_CAPACITY_OUTPUT = (
    "s3://is459-g7-projectbucket/curated/bq1/capacity_evaluation/"
)
DEFAULT_SUMMARY_OUTPUT = (
    "s3://is459-g7-projectbucket/curated/bq1/capacity_summary/"
)
DEFAULT_METRICS_OUTPUT = (
    "s3://is459-g7-projectbucket/metrics/bq1/risk_scoring/"
)
DEFAULT_CAPACITIES = "50,100,500,1000,5000"


# Transparent project assumptions. Each component contributes at most its
# stated number of points, so the final score is always between 0 and 100.
WEIGHTS = {
    "ach_share": 25.0,
    "cross_border_share": 15.0,
    "fan_out": 15.0,
    "fan_in": 15.0,
    "amount_band_share": 10.0,
    "pass_through_share_24h": 10.0,
    "activity_spike_ratio": 10.0,
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles-input", default=DEFAULT_PROFILES_INPUT)
    parser.add_argument("--labels-input", default=DEFAULT_LABELS_INPUT)
    parser.add_argument("--rankings-output", default=DEFAULT_RANKINGS_OUTPUT)
    parser.add_argument("--capacity-output", default=DEFAULT_CAPACITY_OUTPUT)
    parser.add_argument("--summary-output", default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--metrics-output", default=DEFAULT_METRICS_OUTPUT)
    parser.add_argument(
        "--capacities",
        default=DEFAULT_CAPACITIES,
        help="Comma-separated daily investigator capacities",
    )
    parser.add_argument(
        "--run-id",
        default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    )
    return parser.parse_args()


def clean_path(path):
    return path.rstrip("/")


def parse_capacities(raw_capacities):
    try:
        capacities = sorted(
            {int(value.strip()) for value in raw_capacities.split(",")}
        )
    except ValueError as exc:
        raise ValueError("Capacities must be comma-separated integers") from exc

    if not capacities or any(value <= 0 for value in capacities):
        raise ValueError("Every capacity must be a positive integer")
    return capacities


def safe_ratio(numerator, denominator):
    """Return 0 rather than null/division-by-zero for an evaluation ratio."""
    return F.when(
        denominator > 0,
        numerator.cast("double") / denominator.cast("double"),
    ).otherwise(F.lit(0.0))


def main():
    args = parse_args()
    capacities = parse_capacities(args.capacities)
    max_capacity = max(capacities)

    if abs(sum(WEIGHTS.values()) - 100.0) > 1e-9:
        raise ValueError(f"Risk weights must total 100, found {sum(WEIGHTS.values())}")

    started_at = datetime.now(timezone.utc)
    timer_start = time.perf_counter()

    spark = (
        SparkSession.builder.appName("IS459-BQ1-Risk-Scoring")
        .getOrCreate()
    )
    spark.conf.set("spark.sql.adaptive.enabled", "true")
    spark.conf.set("spark.sql.parquet.compression.codec", "snappy")

    profiles = spark.read.parquet(clean_path(args.profiles_input))
    labels = spark.read.parquet(clean_path(args.labels_input))

    required_profile_columns = {
        "profile_date",
        "bank_id",
        "account_id",
        "account_key",
        "txn_count",
        "total_amount_usd",
        "ach_share",
        "cross_border_share",
        "fan_in",
        "fan_out",
        "amount_band_share",
        "pass_through_share_24h",
        "activity_spike_ratio",
    }
    required_label_columns = {
        "profile_date",
        "account_key",
        "account_day_is_laundering",
    }

    missing_profile_columns = sorted(
        required_profile_columns.difference(profiles.columns)
    )
    missing_label_columns = sorted(required_label_columns.difference(labels.columns))
    if missing_profile_columns:
        raise ValueError(
            f"Profiles input is missing required columns: {missing_profile_columns}"
        )
    if missing_label_columns:
        raise ValueError(
            f"Labels input is missing required columns: {missing_label_columns}"
        )

    # Select only fields used by this job. Notice that no laundering label is
    # present in this branch.
    profiles = (
        profiles.select(*sorted(required_profile_columns))
        .persist(StorageLevel.MEMORY_AND_DISK)
    )
    labels = (
        labels.select(*sorted(required_label_columns))
        .persist(StorageLevel.MEMORY_AND_DISK)
    )

    profile_rows = profiles.count()
    label_rows = labels.count()
    if profile_rows == 0:
        raise ValueError("Profiles input contains no rows")
    if profile_rows != label_rows:
        raise ValueError(
            f"Profile/label row mismatch: profiles={profile_rows}, labels={label_rows}"
        )

    invalid_profile_rows = profiles.filter(
        F.col("profile_date").isNull()
        | F.col("account_key").isNull()
        | F.col("bank_id").isNull()
        | F.col("account_id").isNull()
        | F.col("txn_count").isNull()
        | (F.col("txn_count") <= 0)
        | F.col("total_amount_usd").isNull()
        | (F.col("total_amount_usd") < 0)
        | F.col("fan_in").isNull()
        | (F.col("fan_in") < 0)
        | F.col("fan_out").isNull()
        | (F.col("fan_out") < 0)
        | F.col("activity_spike_ratio").isNull()
        | (F.col("activity_spike_ratio") < 0)
        | F.col("ach_share").isNull()
        | (~F.col("ach_share").between(0.0, 1.0))
        | F.col("amount_band_share").isNull()
        | (~F.col("amount_band_share").between(0.0, 1.0))
        | F.col("pass_through_share_24h").isNull()
        | (~F.col("pass_through_share_24h").between(0.0, 1.0))
        | (
            F.col("cross_border_share").isNotNull()
            & (~F.col("cross_border_share").between(0.0, 1.0))
        )
    ).count()
    if invalid_profile_rows:
        raise ValueError(
            f"Found {invalid_profile_rows} invalid account profile rows"
        )

    invalid_label_rows = labels.filter(
        F.col("profile_date").isNull()
        | F.col("account_key").isNull()
        | F.col("account_day_is_laundering").isNull()
        | (~F.col("account_day_is_laundering").isin(0, 1))
    ).count()
    if invalid_label_rows:
        raise ValueError(f"Found {invalid_label_rows} invalid label rows")

    date_bounds = profiles.agg(
        F.min("profile_date").alias("first_date"),
        F.max("profile_date").alias("last_date"),
    ).first()
    first_date = date_bounds["first_date"]
    last_date = date_bounds["last_date"]

    # Fan-in, fan-out and spike are raw counts/ratios with no fixed maximum.
    # Scale each against that day's 95th percentile, then cap at 1. This keeps
    # a few extreme accounts from dominating everybody else's score.
    daily_reference = profiles.groupBy("profile_date").agg(
        F.percentile_approx("fan_in", 0.95, 10000).alias("daily_p95_fan_in"),
        F.percentile_approx("fan_out", 0.95, 10000).alias("daily_p95_fan_out"),
        F.percentile_approx("activity_spike_ratio", 0.95, 10000).alias(
            "daily_p95_activity_spike_ratio"
        ),
    )

    scored = (
        profiles.join(daily_reference, "profile_date", "left")
        .withColumn(
            "fan_in_normalized",
            F.least(
                F.lit(1.0),
                F.col("fan_in").cast("double")
                / F.greatest(F.col("daily_p95_fan_in").cast("double"), F.lit(1.0)),
            ),
        )
        .withColumn(
            "fan_out_normalized",
            F.least(
                F.lit(1.0),
                F.col("fan_out").cast("double")
                / F.greatest(
                    F.col("daily_p95_fan_out").cast("double"), F.lit(1.0)
                ),
            ),
        )
        .withColumn(
            "activity_spike_normalized",
            F.when(
                F.col("daily_p95_activity_spike_ratio") > 1.0,
                F.greatest(
                    F.lit(0.0),
                    F.least(
                        F.lit(1.0),
                        (F.col("activity_spike_ratio") - F.lit(1.0))
                        / (
                            F.col("daily_p95_activity_spike_ratio")
                            - F.lit(1.0)
                        ),
                    ),
                ),
            ).otherwise(F.lit(0.0)),
        )
        .withColumn(
            "ach_points",
            F.col("ach_share") * F.lit(WEIGHTS["ach_share"]),
        )
        .withColumn(
            "cross_border_points",
            F.coalesce(F.col("cross_border_share"), F.lit(0.0))
            * F.lit(WEIGHTS["cross_border_share"]),
        )
        .withColumn(
            "fan_out_points",
            F.col("fan_out_normalized") * F.lit(WEIGHTS["fan_out"]),
        )
        .withColumn(
            "fan_in_points",
            F.col("fan_in_normalized") * F.lit(WEIGHTS["fan_in"]),
        )
        .withColumn(
            "amount_band_points",
            F.col("amount_band_share") * F.lit(WEIGHTS["amount_band_share"]),
        )
        .withColumn(
            "pass_through_points",
            F.col("pass_through_share_24h")
            * F.lit(WEIGHTS["pass_through_share_24h"]),
        )
        .withColumn(
            "activity_spike_points",
            F.col("activity_spike_normalized")
            * F.lit(WEIGHTS["activity_spike_ratio"]),
        )
        .withColumn(
            "risk_score",
            F.round(
                F.col("ach_points")
                + F.col("cross_border_points")
                + F.col("fan_out_points")
                + F.col("fan_in_points")
                + F.col("amount_band_points")
                + F.col("pass_through_points")
                + F.col("activity_spike_points"),
                4,
            ),
        )
    )

    ranking_window = Window.partitionBy("profile_date").orderBy(
        F.col("risk_score").desc(),
        F.col("total_amount_usd").desc(),
        F.col("account_key").asc(),
    )
    day_window = Window.partitionBy("profile_date")

    # This is the operational output for investigators. It deliberately does
    # not contain the ground-truth laundering label.
    rankings = (
        scored.withColumn("daily_rank", F.row_number().over(ranking_window))
        .withColumn("daily_active_accounts", F.count(F.lit(1)).over(day_window))
        .select(
            "profile_date",
            "daily_rank",
            "daily_active_accounts",
            "account_key",
            "bank_id",
            "account_id",
            "risk_score",
            "txn_count",
            "total_amount_usd",
            "ach_share",
            "cross_border_share",
            "fan_in",
            "fan_out",
            "amount_band_share",
            "pass_through_share_24h",
            "activity_spike_ratio",
            "daily_p95_fan_in",
            "daily_p95_fan_out",
            "daily_p95_activity_spike_ratio",
            "fan_in_normalized",
            "fan_out_normalized",
            "activity_spike_normalized",
            "ach_points",
            "cross_border_points",
            "fan_out_points",
            "fan_in_points",
            "amount_band_points",
            "pass_through_points",
            "activity_spike_points",
        )
        .persist(StorageLevel.MEMORY_AND_DISK)
    )

    ranking_rows = rankings.count()
    invalid_score_rows = rankings.filter(
        F.col("risk_score").isNull()
        | (F.col("risk_score") < 0.0)
        | (F.col("risk_score") > 100.0)
    ).count()
    if ranking_rows != profile_rows:
        raise ValueError(
            f"Profile/ranking row mismatch: profiles={profile_rows}, rankings={ranking_rows}"
        )
    if invalid_score_rows:
        raise ValueError(f"Found {invalid_score_rows} risk scores outside 0-100")

    invalid_rank_days = (
        rankings.groupBy("profile_date")
        .agg(
            F.count(F.lit(1)).alias("row_count"),
            F.countDistinct("daily_rank").alias("distinct_rank_count"),
            F.min("daily_rank").alias("min_rank"),
            F.max("daily_rank").alias("max_rank"),
        )
        .filter(
            (F.col("row_count") != F.col("distinct_rank_count"))
            | (F.col("min_rank") != 1)
            | (F.col("max_rank") != F.col("row_count"))
        )
        .count()
    )
    if invalid_rank_days:
        raise ValueError(f"Found {invalid_rank_days} dates with invalid daily ranks")

    # Only now do we join the labels. The score and rank are already fixed.
    evaluated = (
        rankings.join(labels, ["profile_date", "account_key"], "left")
        .persist(StorageLevel.MEMORY_AND_DISK)
    )
    missing_labels = evaluated.filter(
        F.col("account_day_is_laundering").isNull()
    ).count()
    if missing_labels:
        raise ValueError(f"Found {missing_labels} ranked rows without a label")

    daily_laundering_totals = evaluated.groupBy("profile_date").agg(
        F.sum("account_day_is_laundering").alias(
            "total_laundering_account_days"
        )
    )

    capacity_df = spark.createDataFrame(
        [(value,) for value in capacities], ["daily_capacity"]
    )
    selected = (
        evaluated.filter(F.col("daily_rank") <= F.lit(max_capacity))
        .crossJoin(F.broadcast(capacity_df))
        .filter(F.col("daily_rank") <= F.col("daily_capacity"))
    )

    capacity_evaluation = (
        selected.groupBy("profile_date", "daily_capacity")
        .agg(
            F.count(F.lit(1)).alias("accounts_reviewed"),
            F.sum("account_day_is_laundering").alias("laundering_detected"),
            F.min("risk_score").alias("cutoff_score"),
        )
        .join(daily_laundering_totals, "profile_date", "left")
        .withColumn(
            "false_positive_account_days",
            F.col("accounts_reviewed") - F.col("laundering_detected"),
        )
        .withColumn(
            "laundering_missed",
            F.col("total_laundering_account_days")
            - F.col("laundering_detected"),
        )
        .withColumn(
            "precision",
            safe_ratio(F.col("laundering_detected"), F.col("accounts_reviewed")),
        )
        .withColumn(
            "detection_rate",
            safe_ratio(
                F.col("laundering_detected"),
                F.col("total_laundering_account_days"),
            ),
        )
        .persist(StorageLevel.MEMORY_AND_DISK)
    )

    # The median daily cutoff is a practical single starting threshold for a
    # chosen capacity. Daily cutoffs remain available when exact daily queue
    # size is more important than a single fixed threshold.
    capacity_summary_base = capacity_evaluation.groupBy("daily_capacity").agg(
        F.countDistinct("profile_date").alias("days_evaluated"),
        F.sum("accounts_reviewed").alias("total_accounts_reviewed"),
        F.sum("laundering_detected").alias("total_laundering_detected"),
        F.sum("total_laundering_account_days").alias(
            "total_laundering_account_days"
        ),
        F.avg("accounts_reviewed").alias("avg_accounts_reviewed_per_day"),
        F.avg("laundering_detected").alias("avg_laundering_detected_per_day"),
        F.percentile_approx("cutoff_score", 0.5, 10000).alias(
            "recommended_score_threshold"
        ),
        F.min("cutoff_score").alias("min_daily_cutoff_score"),
        F.max("cutoff_score").alias("max_daily_cutoff_score"),
    )
    capacity_summary = (
        capacity_summary_base.withColumn(
            "overall_precision",
            safe_ratio(
                F.col("total_laundering_detected"),
                F.col("total_accounts_reviewed"),
            ),
        )
        .withColumn(
            "overall_detection_rate",
            safe_ratio(
                F.col("total_laundering_detected"),
                F.col("total_laundering_account_days"),
            ),
        )
        .orderBy("daily_capacity")
        .persist(StorageLevel.MEMORY_AND_DISK)
    )

    capacity_rows = capacity_evaluation.count()
    summary_rows = capacity_summary.count()
    expected_summary_rows = len(capacities)
    if summary_rows != expected_summary_rows:
        raise ValueError(
            f"Expected {expected_summary_rows} capacity summary rows, found {summary_rows}"
        )

    (
        rankings.repartition("profile_date")
        .write.mode("overwrite")
        .partitionBy("profile_date")
        .parquet(clean_path(args.rankings_output))
    )
    (
        capacity_evaluation.repartition("profile_date")
        .write.mode("overwrite")
        .partitionBy("profile_date")
        .parquet(clean_path(args.capacity_output))
    )
    (
        capacity_summary.coalesce(1)
        .write.mode("overwrite")
        .parquet(clean_path(args.summary_output))
    )

    finished_at = datetime.now(timezone.utc)
    metrics = {
        "run_id": args.run_id,
        "status": "SUCCEEDED",
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "total_seconds": round(time.perf_counter() - timer_start, 3),
        "profile_rows": profile_rows,
        "label_rows": label_rows,
        "ranking_rows": ranking_rows,
        "capacity_evaluation_rows": capacity_rows,
        "capacity_summary_rows": summary_rows,
        "first_profile_date": str(first_date),
        "last_profile_date": str(last_date),
        "capacities": ",".join(str(value) for value in capacities),
        "weights": ",".join(
            f"{name}:{value:g}" for name, value in WEIGHTS.items()
        ),
        "rankings_output": clean_path(args.rankings_output),
        "capacity_output": clean_path(args.capacity_output),
        "summary_output": clean_path(args.summary_output),
    }
    (
        spark.createDataFrame([metrics])
        .coalesce(1)
        .write.mode("overwrite")
        .json(f"{clean_path(args.metrics_output)}/run_id={args.run_id}")
    )

    capacity_summary.unpersist()
    capacity_evaluation.unpersist()
    evaluated.unpersist()
    rankings.unpersist()
    labels.unpersist()
    profiles.unpersist()
    spark.stop()


if __name__ == "__main__":
    main()
