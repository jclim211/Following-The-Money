"""
IS459 Group 7 | BQ1 Pipeline | Glue Job 2: Account Risk Scoring
---------------------------------------------------------------
Turns cleaned transactions into ONE ROW PER ACCOUNT PER DAY, calculates the
7 behaviours from our weight table, converts each to a 0-1 score
(percentile rank within the day), applies the weights, and ranks accounts
so investigators can review the top N each day.

Risk Score (0-100) = 100 x SUM( weight_i x behaviour_score_i )

Glue job parameters:
  --CLEAN_PATH    s3://<bucket>/clean/transactions/
  --CURATED_PATH  s3://<bucket>/curated/account_day_scores/
  --CONFIG_PATH   s3://<bucket>/config/weights.json
"""
import json
import sys

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# behaviour column -> key in weights.json
BEHAVIOURS = [
    "fan_out",
    "pass_through",
    "fan_in",
    "cross_currency_share",
    "cross_bank_share",
    "activity_spike",
    "payment_format_risk",
]


# ----------------------------------------------------------------- config
def load_config(path: str) -> dict:
    """Read weights.json from S3 (in Glue) or from a local path (testing)."""
    if path.startswith("s3://"):
        import boto3
        bucket, key = path[5:].split("/", 1)
        body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read()
        cfg = json.loads(body)
    else:
        with open(path) as f:
            cfg = json.load(f)

    weights = cfg["weights"]
    missing = [b for b in BEHAVIOURS if b not in weights]
    if missing:
        raise ValueError(f"weights.json is missing: {missing}")
    total = sum(weights[b] for b in BEHAVIOURS)
    if abs(total - 100) > 1e-6:
        raise ValueError(f"Weights must add up to 100, got {total}")
    return cfg


# ------------------------------------------------- step 1: account profiles
def build_legs(tx: DataFrame, risky_formats: list) -> DataFrame:
    """Each transaction appears twice: once for the sender (out) and once for
    the receiver (in), so every account sees all of its own activity."""
    flags = (tx
             .withColumn("is_cross_ccy",
                         (F.col("payment_currency") != F.col("receiving_currency")).cast("int"))
             .withColumn("is_cross_bank",
                         (F.col("from_bank") != F.col("to_bank")).cast("int"))
             .withColumn("is_risky_format",
                         F.col("payment_format").isin(risky_formats).cast("int")))

    common = ["txn_date", "is_cross_ccy", "is_cross_bank", "is_risky_format", "is_laundering"]
    out_legs = flags.select(
        F.col("from_key").alias("account_key"),
        F.col("to_key").alias("counterparty"),
        F.lit("out").alias("direction"),
        F.col("amount_paid").alias("amount"),
        F.col("payment_currency").alias("currency"),
        *common)
    in_legs = flags.select(
        F.col("to_key").alias("account_key"),
        F.col("from_key").alias("counterparty"),
        F.lit("in").alias("direction"),
        F.col("amount_received").alias("amount"),
        F.col("receiving_currency").alias("currency"),
        *common)
    return out_legs.unionByName(in_legs)


def build_profiles(legs: DataFrame) -> DataFrame:
    """One row per account per day with the 7 raw behaviour values."""
    not_self = F.col("counterparty") != F.col("account_key")
    is_out = F.col("direction") == "out"
    is_in = F.col("direction") == "in"

    base = legs.groupBy("account_key", "txn_date").agg(
        F.countDistinct(F.when(is_out & not_self, F.col("counterparty"))).alias("fan_out"),
        F.countDistinct(F.when(is_in & not_self, F.col("counterparty"))).alias("fan_in"),
        F.avg("is_cross_ccy").alias("cross_currency_share"),
        F.avg("is_cross_bank").alias("cross_bank_share"),
        F.avg("is_risky_format").alias("payment_format_risk"),
        F.count(F.lit(1)).alias("n_txn"),
        F.max("is_laundering").alias("is_laundering_account"),  # ground truth
    )

    # Pass-through: how much money came in AND went out on the same day.
    # Compared within each currency so no exchange rates are needed.
    # 1.0 = everything received was sent straight back out.
    by_ccy = legs.groupBy("account_key", "txn_date", "currency").agg(
        F.sum(F.when(is_in, F.col("amount")).otherwise(0.0)).alias("amt_in"),
        F.sum(F.when(is_out, F.col("amount")).otherwise(0.0)).alias("amt_out"))
    pass_through = (by_ccy
                    .groupBy("account_key", "txn_date")
                    .agg(F.sum(F.least("amt_in", "amt_out")).alias("matched"),
                         F.sum(F.greatest("amt_in", "amt_out")).alias("larger"))
                    .withColumn("pass_through",
                                F.when(F.col("larger") > 0,
                                       F.col("matched") / F.col("larger")).otherwise(0.0))
                    .select("account_key", "txn_date", "pass_through"))

    profiles = base.join(pass_through, ["account_key", "txn_date"], "left")

    # Activity spike: today's transaction count vs the account's average day.
    acct_avg = Window.partitionBy("account_key")
    profiles = profiles.withColumn(
        "activity_spike", F.col("n_txn") / F.avg("n_txn").over(acct_avg))

    return profiles.fillna(0.0, subset=["pass_through"])


# ------------------------------------------ step 2: 0-1 scores and weights
def score_and_rank(profiles: DataFrame, weights: dict) -> DataFrame:
    """Percentile-rank each behaviour within the day (0 = lowest, 1 = highest),
    apply the weight table, then rank accounts within each day."""
    scored = profiles
    for b in BEHAVIOURS:
        w = Window.partitionBy("txn_date").orderBy(F.col(b))
        scored = scored.withColumn(f"{b}_score", F.percent_rank().over(w))

    risk = sum(F.lit(weights[b] / 100.0) * F.col(f"{b}_score") for b in BEHAVIOURS)
    scored = scored.withColumn("risk_score", F.round(F.lit(100.0) * risk, 2))

    rank_w = Window.partitionBy("txn_date").orderBy(F.col("risk_score").desc(),
                                                    F.col("account_key"))
    return scored.withColumn("daily_rank", F.row_number().over(rank_w))


def run(spark, clean_path: str, cfg: dict) -> DataFrame:
    tx = spark.read.parquet(clean_path)
    legs = build_legs(tx, cfg.get("high_risk_payment_formats", []))
    profiles = build_profiles(legs)
    return score_and_rank(profiles, cfg["weights"])


def main():
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext

    args = getResolvedOptions(sys.argv,
                              ["JOB_NAME", "CLEAN_PATH", "CURATED_PATH", "CONFIG_PATH"])
    sc = SparkContext.getOrCreate()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    cfg = load_config(args["CONFIG_PATH"])
    result = run(spark, args["CLEAN_PATH"], cfg)

    (result.write
     .mode("overwrite")
     .partitionBy("txn_date")
     .parquet(args["CURATED_PATH"]))

    job.commit()


if __name__ == "__main__":
    main()
