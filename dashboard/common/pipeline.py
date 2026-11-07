"""Uploaded runs and the Start button on the home page.

A run is uploaded straight to S3 as runs/<run>/raw/{transactions,patterns,accounts}/<file>.
Nothing starts on upload: the home page lists every run folder that has not finished yet,
and Start begins the is459-g7-pipeline state machine for it (same input the old upload
trigger, pipeline/orchestration/trigger.py, used to send).

The first execution of a run is named after the run. A retry after a failure is named
<run>__2, <run>__3 and so on. Run names never contain "__", so the run is the part before it.

Anyone who can open the dashboard can press Start. To require a passcode, set
PIPELINE_PASSCODE on the server (or pipeline_passcode in Streamlit secrets).
"""
import hmac
import json
import os
import re
from pathlib import Path

import streamlit as st

from common.athena import BUCKET, REGION, aws_session
from common.runs import list_runs

PIPELINE_ARN = os.getenv(
    "PIPELINE_ARN", f"arn:aws:states:{REGION}:761018854594:stateMachine:is459-g7-pipeline")
REQUIRED = ("transactions", "patterns", "accounts")
RUN_NAME = re.compile(r"[a-z0-9][a-z0-9-]*")
AUTH_KEY = "pipeline_unlocked"


def _passcode() -> str:
    code = os.getenv("PIPELINE_PASSCODE", "")
    if not code:
        try:
            code = str(st.secrets.get("pipeline_passcode", ""))
        except Exception:  # no secrets.toml on this machine
            code = ""
    return code


def passcode_required() -> bool:
    return bool(_passcode())


def _run_of(execution_name: str) -> str:
    return execution_name.split("__", 1)[0]


def _latest_executions(sfn) -> dict:
    """run -> its newest execution (name, status, start, stop), from the last 1000 executions."""
    latest = {}
    pages = sfn.get_paginator("list_executions").paginate(
        stateMachineArn=PIPELINE_ARN, PaginationConfig={"MaxItems": 1000, "PageSize": 100})
    for page in pages:
        for ex in page["executions"]:  # newest first
            run = _run_of(ex["name"])
            if run not in latest:
                latest[run] = {
                    "execution": ex["name"], "status": ex["status"],
                    "started": ex["startDate"].isoformat(),
                    "stopped": ex["stopDate"].isoformat() if ex.get("stopDate") else None,
                }
    return latest


@st.cache_data(ttl=20, show_spinner=False)
def list_uploads() -> list:
    """Every runs/<run>/ folder that has no run.json yet, newest upload first.

    status: incomplete (a raw file is missing), ready, running, failed, or succeeded
    (the execution finished but run.json is not readable yet).
    """
    mock = os.getenv("DASHBOARD_MOCK_DIR")
    if mock:
        path = Path(mock) / "uploads.json"
        return json.loads(path.read_text()) if path.exists() else []

    s3, sfn = aws_session().client("s3"), aws_session().client("stepfunctions")
    folders = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix="runs/", Delimiter="/"):
        folders += [p["Prefix"].split("/")[1] for p in page.get("CommonPrefixes", [])]

    finished = {r["run"] for r in list_runs()}  # finished runs are listed there already
    executions = _latest_executions(sfn)
    uploads = []
    for run in folders:
        if run in finished:
            continue
        files, uploaded = {}, None
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=f"runs/{run}/raw/"):
            for item in page.get("Contents", []):
                parts = item["Key"][len(f"runs/{run}/raw/"):].split("/")
                if len(parts) == 2 and parts[0] in REQUIRED and parts[1] and item["Size"] > 0:
                    files.setdefault(parts[0], {"name": parts[1], "mb": round(item["Size"] / 1e6, 1)})
                    when = item["LastModified"].isoformat()
                    uploaded = max(uploaded or when, when)

        ex = executions.get(run)
        missing = [f for f in REQUIRED if f not in files]
        if ex and ex["status"] == "RUNNING":
            status = "running"
        elif ex and ex["status"] in ("FAILED", "TIMED_OUT", "ABORTED"):
            status = "failed"
        elif ex and ex["status"] == "SUCCEEDED":
            status = "succeeded"
        elif missing:
            status = "incomplete"
        else:
            status = "ready"
        uploads.append({
            "run": run, "status": status, "valid_name": bool(RUN_NAME.fullmatch(run)),
            "files": files, "missing": missing, "uploaded": uploaded,
            "dataset": files["transactions"]["name"].split("_")[0] if "transactions" in files else None,
            "execution": ex,
        })
    return sorted(uploads, key=lambda u: u["uploaded"] or "", reverse=True)


def start_run(run: str, passcode: str = "") -> tuple:
    """Start the pipeline for an uploaded run. Returns (ok, message)."""
    if not RUN_NAME.fullmatch(run or ""):
        return False, "Run names use lowercase letters, numbers and hyphens only."
    code = _passcode()
    if code and not st.session_state.get(AUTH_KEY):
        if not hmac.compare_digest(str(passcode or ""), code):
            return False, "That passcode is not right."
        st.session_state[AUTH_KEY] = True

    upload = next((u for u in list_uploads() if u["run"] == run), None)
    if upload is None:
        return False, f"{run} is not in the upload list any more. It may have finished."
    if upload["status"] == "running":
        return False, f"{run} is already running."
    if upload["missing"]:
        return False, f"{run} is still missing: {', '.join(upload['missing'])}."

    if os.getenv("DASHBOARD_MOCK_DIR"):
        return True, f"Started {run} (mock, nothing was sent to AWS)."

    sfn = aws_session().client("stepfunctions")
    tries = 0
    for page in sfn.get_paginator("list_executions").paginate(stateMachineArn=PIPELINE_ARN):
        tries += sum(1 for ex in page["executions"] if _run_of(ex["name"]) == run)
    name = run if tries == 0 else f"{run}__{tries + 1}"
    run_input = {"run": run, "db": "aml_" + run.replace("-", "_"), "dataset": upload["dataset"]}
    try:
        sfn.start_execution(stateMachineArn=PIPELINE_ARN, name=name, input=json.dumps(run_input))
    except sfn.exceptions.ExecutionAlreadyExists:
        return False, f"{run} was started a moment ago by someone else."
    list_uploads.clear()
    return True, f"Started {run} ({upload['dataset']}). It usually takes 15 to 30 minutes."
