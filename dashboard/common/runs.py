"""Finished pipeline runs. Each run lives in runs/<run>/ with its own Glue database.

A run counts as finished once runs/<run>/run.json exists, because the pipeline writes
that file last. Home.py builds the sidebar from list_runs() and sets the open run.
"""
import json

import streamlit as st
from botocore.exceptions import ClientError

from common.athena import BUCKET, aws_session

RUN_KEY = "open_run"


@st.cache_data(ttl=60, show_spinner=False)
def list_runs() -> list:
    """Finished runs, newest first."""
    s3 = aws_session().client("s3")
    folders = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="runs/", Delimiter="/"):
        folders += [p["Prefix"] for p in page.get("CommonPrefixes", [])]
    runs = []
    for folder in folders:
        try:
            body = s3.get_object(Bucket=BUCKET, Key=f"{folder}run.json")["Body"].read()
        except ClientError:  # still running, or failed
            continue
        runs.append(json.loads(body))
    return sorted(runs, key=lambda r: r["finished"], reverse=True)


def open_run():
    """The run this page is showing, or None for the original HI-Medium tables."""
    return st.session_state.get(RUN_KEY)
