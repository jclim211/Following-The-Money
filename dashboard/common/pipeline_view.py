"""Pipeline view: which step of is459-g7-pipeline is running, the flow of a run, and its Spark jobs.

MOCK ONLY for now: every number here is generated sample data, so the design can be reviewed
before the dashboard role gets read access to the execution history (states:GetExecutionHistory,
states:DescribeExecution), the EMR Serverless job runs (emr-serverless:GetJobRun) and the
runs/<run>/metrics/ files. The shapes below are what the live version will return.

flow  = {"run", "execution", "status": RUNNING|SUCCEEDED|FAILED, "started", "stopped",
         "steps": {step_id: {"state": done|running|failed|cancelled|pending|skipped, "start", "end",
                             "error"?, "checks"?}}}
spark = {"kind": "spark", "meta": {...}, "flow": flow, "jobs": [one dict per Spark job]}
"""
from __future__ import annotations

import os
import zlib
from datetime import datetime, timedelta, timezone

# Seconds per step for HI-Small (matches the observed ~12 minute run); other sizes scale.
BASE = {"start": 3, "database": 2, "clean": 260, "bq1profiles": 190, "bq1scoring": 140,
        "bq2schemes": 120, "bq2analysis": 230, "crawler": 105, "lookup": 25, "view": 3, "record": 1}
SIZE = {"HI-Small": 1.0, "LI-Small": 1.15, "HI-Medium": 1.5, "LI-Medium": 1.5, "HI-Large": 5.5, "LI-Large": 5.5}
ROWS = {"HI-Small": 5_078_345, "LI-Small": 6_924_049, "HI-Medium": 31_898_238, "LI-Medium": 31_251_483,
        "HI-Large": 179_702_229, "LI-Large": 176_066_557}
JOBS = [("clean", "Clean transactions", "scripts/shared/clean.py", 16, 64),
        ("bq1profiles", "BQ1 account profiles", "scripts/bq1/account_profiles.py", 12, 48),
        ("bq1scoring", "BQ1 risk scoring", "scripts/bq1/risk_scoring.py", 12, 48),
        ("bq2schemes", "BQ2 schemes", "scripts/bq2/schemes.py", 8, 32),
        ("bq2analysis", "BQ2 analysis", "scripts/bq2/bq2_analysis_v2.py", 16, 64)]
VCPU_RATE, GB_RATE = 0.042094, 0.004628  # EMR Serverless arm64, USD per vCPU-hour and GB-hour


def _iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse(s: str) -> datetime:
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _offsets(scale: float) -> dict:
    """step -> (start, end) seconds from the execution start."""
    d = {k: v * scale for k, v in BASE.items()}
    out, t = {}, 0.0
    for k in ("start", "database", "clean"):
        out[k] = (t, t + d[k]); t += d[k]
    b1 = (t, t + d["bq1profiles"]); out["bq1profiles"] = b1
    out["bq1scoring"] = (b1[1], b1[1] + d["bq1scoring"])
    b2 = (t, t + d["bq2schemes"]); out["bq2schemes"] = b2
    out["bq2analysis"] = (b2[1], b2[1] + d["bq2analysis"])
    t = max(out["bq1scoring"][1], out["bq2analysis"][1])
    for k in ("crawler", "lookup", "view", "record"):
        out[k] = (t, t + d[k]); t += d[k]
    return out


def total_seconds(scale: float = 1.0) -> float:
    return _offsets(scale)["record"][1]


def mock_flow(run: str, dataset: str, started: datetime, status: str, scale: float | None = None,
              now: datetime | None = None, fail_at: str | None = None, execution: str | None = None) -> dict:
    scale = scale or SIZE.get(dataset, 1.0)
    off = _offsets(scale)
    now = now or datetime.now(timezone.utc)
    elapsed = (now - started).total_seconds() if status == "RUNNING" else float("inf")
    if status == "RUNNING":  # keep the last step running until the execution really ends
        elapsed = min(elapsed, off["record"][0] + 0.5)
    steps = {"upload": {"state": "done", "start": _iso(started - timedelta(minutes=4)), "end": _iso(started - timedelta(minutes=3))}}
    failed_end = None
    if fail_at:
        failed_end = off[fail_at][0] + (off[fail_at][1] - off[fail_at][0]) * 0.35
    for k, (a, b) in off.items():
        s = {"start": _iso(started + timedelta(seconds=a)), "end": _iso(started + timedelta(seconds=b))}
        if fail_at:
            if k == fail_at:
                s.update(state="failed", end=_iso(started + timedelta(seconds=failed_end)),
                         error=f"EMR Serverless job run {k.replace('bq2', 'bq2-').replace('bq1', 'bq1-')}-{run} failed: "
                               "Job failed, please check complete logs in configured logging destination. ExitCode: 1. "
                               "Last few exceptions: java.lang.OutOfMemoryError: Java heap space")
            elif b <= failed_end:
                s["state"] = "done"
            elif a < failed_end:  # Step Functions stops the other branch when one fails
                s.update(state="cancelled", end=_iso(started + timedelta(seconds=failed_end)),
                         error="Stopped by Step Functions because the BQ2 branch failed.")
            else:
                s = {"state": "skipped"}
        elif b <= elapsed:
            s["state"] = "done"
        elif a <= elapsed:
            s.update(state="running", end=None)
        else:
            s = {"state": "pending"}
        if k == "crawler" and s.get("state") in ("done", "running"):
            s["checks"] = max(1, int(((min(b, elapsed) - a) // 20) + 1))
        steps[k] = s
    end = None
    if status == "SUCCEEDED":
        end = _iso(started + timedelta(seconds=off["record"][1]))
    elif fail_at:
        end = _iso(started + timedelta(seconds=failed_end))
    return {"run": run, "execution": execution or run, "status": status, "dataset": dataset,
            "started": _iso(started), "stopped": end, "steps": steps}


_ANCHOR: dict = {}


def _running_start(run: str, dataset: str, now: datetime) -> datetime:
    """A start time that keeps the running sample moving: it opens inside the Spark branches,
    advances in real time, and starts over once the sample run would have finished."""
    scale = SIZE.get(dataset, 1.0)
    t0 = _ANCHOR.get(run)
    if t0 is None or (now - t0).total_seconds() > total_seconds(scale):
        t0 = _ANCHOR[run] = now - timedelta(seconds=_offsets(scale)["clean"][1] + 420)
    return t0


def mock_flows(runs: list, uploads: list, now: datetime | None = None) -> dict:
    """Sample flows for the home page: finished runs fit their real start and finish times."""
    now = now or datetime.now(timezone.utc)
    flows = {}
    for r in runs:
        a, b = _parse(r["started"]), _parse(r["finished"])
        scale = max(0.05, (b - a).total_seconds() / total_seconds())
        flows[r["run"]] = mock_flow(r["run"], r["dataset"], a, "SUCCEEDED", scale=scale, execution=r.get("execution"))
    for u in uploads:
        ex, ds = u.get("execution"), u.get("dataset") or "HI-Small"
        if u["status"] == "running" and ex:
            if os.getenv("DASHBOARD_MOCK_DIR"):
                started = _running_start(u["run"], ds, now)
            else:  # a real run: sample progress from its real start time
                started = _parse(ex["started"])
            if os.getenv("DASHBOARD_MOCK_DIR"):
                ex["started"] = _iso(started)
            flows[u["run"]] = mock_flow(u["run"], ds, started, "RUNNING", now=now, execution=ex["execution"])
        elif u["status"] == "failed" and ex:
            flows[u["run"]] = mock_flow(u["run"], ds, _parse(ex["started"]), "FAILED", fail_at="bq2analysis",
                                        execution=ex["execution"])
    return flows


def _job_metrics(job: str, dataset: str) -> tuple[list, list, int, int]:
    """(metrics, stage timings, rows in, rows out) in the shape the jobs' metrics JSON has."""
    n = ROWS.get(dataset, ROWS["HI-Small"])
    f = n / ROWS["HI-Small"]
    clean = int(n * 0.9957)
    acct_days = int(1_846_212 * f)
    if job == "clean":
        return ([["Raw transactions", n, "Rows read from raw/transactions"], ["Duplicates dropped", int(9 * f), "Exact copies"],
                 ["Self-transfers dropped", int(20_712 * f), "Same account on both sides"],
                 ["Days kept", "16 of 18", "Thin tail cut at 10% of the median day"], ["Banks", int(30_470 * min(f, 3)), "clean/banks"]],
                [["Read CSV", 38], ["Deduplicate", 41], ["Cut the tail", 12], ["USD and countries", 29], ["Write Parquet", 64]], n, clean)
    if job == "bq1profiles":
        return ([["Account-days profiled", acct_days, "One row per account per day"], ["Accounts", int(515_080 * f), "Seen at least once"],
                 ["Behaviours", 7, "ACH, cross-border, fan-in, fan-out, band, pass-through, spike"], ["Labels kept apart", acct_days, "account_labels, evaluation only"]],
                [["Read clean data", 22], ["Build legs", 31], ["Daily profiles", 58], ["Pass-through 24h", 44], ["Write Parquet", 25]], clean, acct_days)
    if job == "bq1scoring":
        return ([["Account-days scored", acct_days, "0 to 100 points"], ["Capacities tested", 5, "50, 100, 500, 1000, 5000 a day"],
                 ["Days evaluated", 16, "Labels joined after ranking"], ["Top 1000 rows / day", 16_000, "Feeds bq1_dashboard_queue"]],
                [["Read profiles", 14], ["Score", 26], ["Rank per day", 33], ["Capacity evaluation", 41], ["Write Parquet", 18]], acct_days, acct_days)
    if job == "bq2schemes":
        sch, tr = int(370 * f), int(2_156 * f)
        return ([["Schemes parsed", sch, "From Patterns.txt"], ["Scheme transfers", tr, "One row each"],
                 ["Matched to clean data", "97.4%", "in_clean flag"], ["Scheme types", 8, "Fan-out, fan-in, cycle, ..."]],
                [["Read Patterns.txt", 6], ["Parse blocks", 9], ["Add USD and countries", 14], ["Match transactions", 52], ["Write Parquet", 11]], tr, tr)
    return ([["Tables written", 6, "Six small tables in curated/bq2/"], ["Laundering transfers", int(5_177 * f), "is_laundering = 1"],
             ["Banks scored", int(30_470 * min(f, 3)), "bank_entry_exit"], ["Country pairs", 42, "country_pairs"]],
            [["Read clean data", 24], ["Flow comparison", 37], ["Holding time", 71], ["Entry and exit banks", 46], ["Write Parquet", 19]],
            clean, int(9_412 * f))


def mock_spark_payload(run: dict, now: datetime | None = None) -> dict:
    a, b = _parse(run["started"]), _parse(run["finished"])
    scale = max(0.05, (b - a).total_seconds() / total_seconds())
    flow = mock_flow(run["run"], run["dataset"], a, "SUCCEEDED", scale=scale, execution=run.get("execution"))
    jobs = []
    for i, (jid, name, script, vcpu, gb) in enumerate(JOBS):
        st = flow["steps"][jid]
        secs = (_parse(st["end"]) - _parse(st["start"])).total_seconds()
        vcpu_h, gb_h = round(vcpu * secs / 3600, 3), round(gb * secs / 3600, 3)
        metrics, stages, rin, rout = _job_metrics(jid, run["dataset"])
        tot = sum(s for _, s in stages)
        jobs.append({"id": jid, "name": name, "script": script, "state": "SUCCESS",
                     "job_run_id": f"00g9{zlib.crc32((run['run'] + jid).encode()):08x}k{i}",
                     "job_name": f"{jid.replace('bq1', 'bq1-').replace('bq2', 'bq2-')}-{run['run']}",
                     "start": st["start"], "end": st["end"], "seconds": round(secs),
                     "workers": f"{vcpu // 4 - 1} worker{'s' if vcpu // 4 - 1 != 1 else ''} + driver, {vcpu} vCPU, {gb} GB",
                     "vcpu_h": vcpu_h, "gb_h": gb_h, "cost": round(vcpu_h * VCPU_RATE + gb_h * GB_RATE, 4),
                     "rows_in": rin, "rows_out": rout, "metrics": metrics,
                     "stages": [[s, round(v * secs / tot)] for s, v in stages]})
    return {"kind": "spark", "meta": {"dataset": run["dataset"], "db": run["db"], "mock": True,
                                      "rates": {"vcpu": VCPU_RATE, "gb": GB_RATE}},
            "flow": flow, "jobs": jobs}
