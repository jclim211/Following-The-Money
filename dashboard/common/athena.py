"""
Shared Athena + S3 helper for the BQ1 dashboard pages.

Flow: SQL file in S3 -> Athena runs it and writes a CSV to S3 -> Streamlit reads that CSV from S3.

    from common.athena import run_query
    df = run_query("queue_top_accounts", {"profile_date": "2022-09-16", "top_n": 100})

Locally it uses AWS profile `is459`. On EC2 it uses the instance role
(BQ1_AWS_PROFILE is set to empty there). Results are cached for an hour,
and Athena also reuses identical results for 60 minutes to keep costs low.
"""
import os
import re
import time

import boto3
import pandas as pd
import streamlit as st
from botocore.exceptions import ProfileNotFound

REGION = os.getenv("BQ1_REGION", "us-east-1")
PROFILE = os.getenv("BQ1_AWS_PROFILE", "is459")
WORKGROUP = "primary"
BUCKET = "is459-g7-projectbucket"
QUERY_PREFIX = "scripts/queries"
ATHENA_OUTPUT = f"s3://{BUCKET}/athena-results"


@st.cache_resource
def aws_session():
    try:
        return boto3.Session(profile_name=PROFILE, region_name=REGION) if PROFILE else boto3.Session(region_name=REGION)
    except ProfileNotFound:
        return boto3.Session(region_name=REGION)


@st.cache_data(ttl=3600, show_spinner=False)
def load_sql(path: str) -> str:
    """Read a stored query from S3, e.g. path = bq1/dashboard/capacity_summary."""
    obj = aws_session().client("s3").get_object(Bucket=BUCKET, Key=f"{QUERY_PREFIX}/{path}.sql")
    return obj["Body"].read().decode("utf-8")


def fill_placeholders(sql: str, params: dict) -> str:
    """Put values into the SQL. Callers pass only validated values, never raw free text."""
    for key, value in params.items():
        sql = sql.replace("{" + key + "}", str(value))
    left = re.findall(r"\{[a-z_]+\}", sql)
    if left:
        raise ValueError(f"Stored query still has unfilled placeholders: {sorted(set(left))}")
    return sql


def run_query(name: str, params: dict = None, database: str = None,
              folder: str = "bq1/dashboard", text_columns: tuple = ()) -> pd.DataFrame:
    """Run a stored read-only query and read its result CSV from S3.

    database defaults to the BQ1 database of the run picked in the header
    (aml_curated for Run 1). Columns named in text_columns are left as text
    (for IDs such as bank_id that look numeric but must keep their exact spelling).
    """
    if database is None:
        from common.runs import current_run
        run = current_run()
        database = run.db("bq1", "aml_curated") if run else "aml_curated"
    return _run_query(name, params, database, folder, text_columns)


def mock_result(folder: str, name: str):
    """Local UI testing without AWS: DASHBOARD_MOCK_DIR=<dir> reads <dir>/<folder>/<name>.csv."""
    mock_dir = os.getenv("DASHBOARD_MOCK_DIR")
    if not mock_dir:
        return None
    return pd.read_csv(os.path.join(mock_dir, folder, f"{name}.csv"))


@st.cache_data(ttl=3600, show_spinner="Querying Athena...")
def _run_query(name: str, params: dict, database: str, folder: str, text_columns: tuple) -> pd.DataFrame:
    mocked = mock_result(folder, name)
    if mocked is not None:
        return mocked
    session = aws_session()
    athena = session.client("athena")
    qid = athena.start_query_execution(
        QueryString=fill_placeholders(load_sql(f"{folder}/{name}"), params or {}),
        QueryExecutionContext={"Database": database},
        WorkGroup=WORKGROUP,
        ResultConfiguration={"OutputLocation": f"{ATHENA_OUTPUT}/{folder}/{name}/"},
        ResultReuseConfiguration={"ResultReuseByAgeConfiguration": {"Enabled": True, "MaxAgeInMinutes": 60}},
    )["QueryExecutionId"]

    while True:
        execution = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        status = execution["Status"]
        if status["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.5)
    if status["State"] != "SUCCEEDED":
        raise RuntimeError(status.get("StateChangeReason", status["State"]))

    # A reused result can live in an older folder, so always use the location Athena reports.
    bucket, key = execution["ResultConfiguration"]["OutputLocation"].removeprefix("s3://").split("/", 1)
    body = session.client("s3").get_object(Bucket=bucket, Key=key)["Body"]
    df = pd.read_csv(body, dtype=str, keep_default_na=False, na_values=[""])
    for col in df.columns:  # CSV is text; turn numeric columns into numbers
        if col in text_columns:
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() == df[col].notna().sum():
            df[col] = converted
    return df
