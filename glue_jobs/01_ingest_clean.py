"""
IS459 Group 7 | BQ1 Pipeline | Glue Job 1: Ingest and Clean
-----------------------------------------------------------
Reads the raw IBM AML transactions CSV from the S3 RAW zone, cleans it,
and writes it to the S3 CLEAN zone as Parquet, partitioned by date.

Why: Parquet + date partitions make later Spark jobs and Athena queries
faster and cheaper (Athena charges by data scanned).

Glue job parameters (set in Job details > Advanced > Job parameters):
  --RAW_PATH    e.g. s3://<bucket>/raw/HI-Medium_Trans.csv
  --CLEAN_PATH  e.g. s3://<bucket>/clean/transactions/
"""
import sys

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (DoubleType, IntegerType, StringType,
                               StructField, StructType)

# The Kaggle CSV has two columns both called "Account" (sender and receiver),
# so we supply our own schema with clear names instead of trusting the header.
RAW_SCHEMA = StructType([
    StructField("timestamp_str", StringType()),
    StructField("from_bank", StringType()),
    StructField("from_account", StringType()),
    StructField("to_bank", StringType()),
    StructField("to_account", StringType()),
    StructField("amount_received", DoubleType()),
    StructField("receiving_currency", StringType()),
    StructField("amount_paid", DoubleType()),
    StructField("payment_currency", StringType()),
    StructField("payment_format", StringType()),
    StructField("is_laundering", IntegerType()),
])


def read_raw(spark: SparkSession, raw_path: str) -> DataFrame:
    return (spark.read
            .option("header", "true")      # skip the header line
            .option("enforceSchema", "true")  # use our column names
            .schema(RAW_SCHEMA)
            .csv(raw_path))


def clean(df: DataFrame) -> DataFrame:
    """Parse timestamps, build unique account keys, drop bad rows."""
    df = (df
          .withColumn("ts", F.to_timestamp("timestamp_str", "yyyy/MM/dd HH:mm"))
          .withColumn("txn_date", F.to_date("ts"))
          # Account numbers are only unique within a bank, so key = bank + account
          .withColumn("from_key", F.concat_ws("_", "from_bank", "from_account"))
          .withColumn("to_key", F.concat_ws("_", "to_bank", "to_account"))
          .drop("timestamp_str"))

    # Basic data quality rules
    df = df.filter(F.col("ts").isNotNull()
                   & F.col("from_key").isNotNull()
                   & F.col("to_key").isNotNull()
                   & (F.col("amount_paid") >= 0)
                   & (F.col("amount_received") >= 0))
    return df


def main():
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext

    args = getResolvedOptions(sys.argv, ["JOB_NAME", "RAW_PATH", "CLEAN_PATH"])
    sc = SparkContext.getOrCreate()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    raw = read_raw(spark, args["RAW_PATH"])
    cleaned = clean(raw)

    (cleaned.write
     .mode("overwrite")
     .partitionBy("txn_date")
     .parquet(args["CLEAN_PATH"]))

    job.commit()


if __name__ == "__main__":
    main()
