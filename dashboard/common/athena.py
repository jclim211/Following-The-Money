"""
Shared Athena helper for every dashboard page (BQ1 and BQ2).

    from common.athena import run_query
    df = run_query("SELECT ... FROM risk_rankings", database="aml_curated")

Locally it uses AWS profile `is459`. On EC2 it uses the instance role
(BQ1_AWS_PROFILE is set to empty there). Results are cached for an hour,
and Athena also reuses identical results for 60 minutes to keep costs low.
"""
import os
import time

import boto3
import pandas as pd
import streamlit as st
from botocore.exceptions import ProfileNotFound

REGION = os.getenv("BQ1_REGION", "us-east-1")
PROFILE = os.getenv("BQ1_AWS_PROFILE", "is459")
WORKGROUP = "primary"
ATHENA_OUTPUT = "s3://is459-g7-projectbucket/athena-results/streamlit/"


@st.cache_resource
def athena_client():
    try:
        session = boto3.Session(profile_name=PROFILE, region_name=REGION) if PROFILE else boto3.Session(region_name=REGION)
    except ProfileNotFound:
        session = boto3.Session(region_name=REGION)
    return session.client("athena")


@st.cache_data(ttl=3600, show_spinner="Querying Athena...")
def run_query(sql: str, database: str = "aml_curated") -> pd.DataFrame:
    """Run a read-only query and return the result as a DataFrame."""
    athena = athena_client()
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        WorkGroup=WORKGROUP,
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
        ResultReuseConfiguration={"ResultReuseByAgeConfiguration": {"Enabled": True, "MaxAgeInMinutes": 60}},
    )["QueryExecutionId"]

    while True:
        status = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        if status["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.5)
    if status["State"] != "SUCCEEDED":
        raise RuntimeError(status.get("StateChangeReason", status["State"]))

    rows, token = [], None
    while True:
        kwargs = {"QueryExecutionId": qid, "MaxResults": 1000}
        if token:
            kwargs["NextToken"] = token
        page = athena.get_query_results(**kwargs)
        rows.extend(page["ResultSet"]["Rows"])
        token = page.get("NextToken")
        if not token:
            break
    header = [c.get("VarCharValue") for c in rows[0]["Data"]]
    df = pd.DataFrame([[c.get("VarCharValue") for c in r["Data"]] for r in rows[1:]], columns=header)
    for col in df.columns:  # Athena returns text; turn numeric columns into numbers
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() == df[col].notna().sum():
            df[col] = converted
    return df
