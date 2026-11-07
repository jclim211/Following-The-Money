"""NO LONGER USED: its EventBridge rule is disabled by infra/ and runs start from the
dashboard (dashboard/common/pipeline.py). Kept for reference.

Starts is459-g7-pipeline when a run has all its required files.

EventBridge calls this for every new file under runs/<run>/raw/. The pipeline
starts only once transactions, patterns and accounts all have a file. The
execution is named after the run, so a run can only ever start once.
"""
import json
import re

import boto3

BUCKET = "is459-g7-projectbucket"
PIPELINE = "arn:aws:states:us-east-1:761018854594:stateMachine:is459-g7-pipeline"
REQUIRED = ("transactions", "patterns", "accounts")

s3 = boto3.client("s3")
stepfunctions = boto3.client("stepfunctions")


def first_file(run, folder):
    """Return the name of the first non-empty file in a raw folder, or None."""
    listing = s3.list_objects_v2(Bucket=BUCKET, Prefix=f"runs/{run}/raw/{folder}/")
    for item in listing.get("Contents", []):
        if item["Size"] > 0:
            return item["Key"].rsplit("/", 1)[-1]
    return None


def handler(event, context):
    key = event["detail"]["object"]["key"]
    match = re.fullmatch(r"runs/([a-z0-9][a-z0-9-]*)/raw/[^/]+/[^/]+", key)
    if not match:
        print(f"Ignored {key}: run names use lowercase letters, numbers and hyphens")
        return "ignored"
    run = match.group(1)

    files = {folder: first_file(run, folder) for folder in REQUIRED}
    missing = [folder for folder, name in files.items() if name is None]
    if missing:
        print(f"Run {run} is waiting for: {', '.join(missing)}")
        return "waiting"

    run_input = {
        "run": run,
        "db": "aml_" + run.replace("-", "_"),
        "dataset": files["transactions"].split("_")[0],  # HI-Small_Trans.csv -> HI-Small
    }
    try:
        stepfunctions.start_execution(stateMachineArn=PIPELINE, name=run, input=json.dumps(run_input))
    except stepfunctions.exceptions.ExecutionAlreadyExists:
        print(f"Run {run} has already started, so nothing was done")
        return "already started"
    print(f"Started run {run}: {run_input}")
    return "started"
