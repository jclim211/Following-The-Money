"""Data for the new dashboard design (common/ui.py): the same stored Athena queries as the
classic BQ1 and BQ2 pages, packed into the JSON the front end in ui/frontend/ reads.

One payload per page and run, cached for an hour like the classic pages. The queries of a page
run in parallel, so a cold load waits for the slowest query instead of the sum of all of them.
Athena also reuses identical results for 60 minutes, so the cost is the same as the classic pages.

Set DASHBOARD_MOCK_DIR=tests/mock_athena to run the design locally without AWS.
"""
from __future__ import annotations

import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import streamlit as st

from common.athena import ATHENA_OUTPUT, BUCKET, WORKGROUP, aws_session, fill_placeholders

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # bq1_data.py sits in dashboard/
import bq1_data as bd  # noqa: E402

DATA_DIR = Path(os.environ.get("BQ1_DATA_DIR", Path(__file__).resolve().parents[1] / "data_bq1"))
BQ1_TEXT_COLUMNS = ("profile_date", "bank_id", "account_id", "account_key", "account_country")
BQ2_QUERIES = ["flow_comparison", "scheme_profile", "holding_time", "country_pairs", "bank_entry_exit",
               "scheme_edges", "bank_size"]


# ---------------------------------------------------------------- Athena
def _numbers(df: pd.DataFrame, text_columns=()) -> pd.DataFrame:
    """CSV is text; turn columns that are all numbers into numbers (as common.athena.run_query does)."""
    for col in df.columns:
        if col in text_columns:
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() == df[col].notna().sum():
            df[col] = converted
    return df


def _mock(name: str) -> pd.DataFrame:
    mock = Path(os.environ["DASHBOARD_MOCK_DIR"])
    path = {"dashboard_queue": DATA_DIR / bd.QUEUE_FILE, "capacity_summary": DATA_DIR / bd.CAPACITY_FILE}.get(
        name, mock / "bq2" / "dashboard" / f"{name}.csv")
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def _sql(key: str) -> str:
    obj = aws_session().client("s3").get_object(Bucket=BUCKET, Key=f"{key}.sql")
    return obj["Body"].read().decode("utf-8")


def _athena(athena, s3, name: str, sql: str, database: str, output: str, text_columns=()) -> pd.DataFrame:
    """Run one read-only query and read its result CSV from S3 (the flow of common.athena.run_query)."""
    if os.getenv("DASHBOARD_MOCK_DIR"):
        return _numbers(_mock(name), text_columns)
    qid = athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        WorkGroup=WORKGROUP,
        ResultConfiguration={"OutputLocation": f"{output}/{name}/"},
        ResultReuseConfiguration={"ResultReuseByAgeConfiguration": {"Enabled": True, "MaxAgeInMinutes": 60}},
    )["QueryExecutionId"]
    while True:
        execution = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        status = execution["Status"]
        if status["State"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.5)
    if status["State"] != "SUCCEEDED":
        raise RuntimeError(f"{name}: {status.get('StateChangeReason', status['State'])}")
    bucket, key = execution["ResultConfiguration"]["OutputLocation"].removeprefix("s3://").split("/", 1)
    body = s3.get_object(Bucket=bucket, Key=key)["Body"]
    return _numbers(pd.read_csv(body, dtype=str, keep_default_na=False, na_values=[""]), text_columns)


def _run_all(jobs: dict, database: str, output: str, text_columns=()) -> dict:
    """jobs = {name: sql}. Returns {name: DataFrame or the exception it raised}."""
    mock = bool(os.getenv("DASHBOARD_MOCK_DIR"))
    session = aws_session()
    athena = None if mock else session.client("athena")
    s3 = None if mock else session.client("s3")
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {n: pool.submit(_athena, athena, s3, n, sql, database, output, text_columns) for n, sql in jobs.items()}
    out = {}
    for name, fut in futures.items():
        try:
            out[name] = fut.result()
        except Exception as err:  # reported per query; the caller decides what is fatal
            out[name] = err
    return out


def _value(v, digits=None):
    """JSON-safe number: None for NaN/NA, rounded when asked."""
    if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)):
        return None
    if digits is None:
        return int(v)
    return round(float(v), digits)


def _records(df: pd.DataFrame) -> list:
    return [{k: (None if (isinstance(v, float) and math.isnan(v)) else v) for k, v in row.items()}
            for row in df.astype(object).where(df.notna(), None).to_dict("records")]


# ---------------------------------------------------------------- BQ2
@st.cache_data(ttl=3600, show_spinner=False)
def bq2_payload(run: dict | None) -> dict:
    """flow, holding time, scheme types, routes, entry/exit banks, scheme edges and bank sizes."""
    db = run["db"] if run else "aml_bq2_curated"
    prefix = "scripts/queries/run" if run else "scripts/queries/bq2/dashboard"
    output = (f"s3://{BUCKET}/athena-results/runs/{run['run']}/dashboard" if run
              else f"s3://{BUCKET}/athena-results/bq2/dashboard")
    names = BQ2_QUERIES + (["date_range"] if run else [])
    mock = bool(os.getenv("DASHBOARD_MOCK_DIR"))
    jobs = {n: "" if mock else _sql(f"{prefix}/{n}").replace("{db}", db) for n in names}
    res = _run_all(jobs, db, output)
    failed = {n: r for n, r in res.items() if isinstance(r, Exception) and n != "bank_size"}
    if failed:
        raise RuntimeError("; ".join(f"{n}: {str(e)[:200]}" for n, e in failed.items()))

    flow, profile, hold = res["flow_comparison"], res["scheme_profile"], res["holding_time"]
    pairs, bee, edges = res["country_pairs"], res["bank_entry_exit"], res["scheme_edges"]
    size = res["bank_size"]
    if isinstance(size, Exception):  # as on the classic page: keep going with names only
        size = bee[["bank_id", "bank_name", "country"]].assign(total_txns=0, n_accounts=0)
    if run:
        d = res["date_range"].iloc[0]
        dataset, first_day, last_day = run["dataset"], str(d["first_day"]), str(d["last_day"])
    else:
        dataset, first_day, last_day = "HI-Medium", "2022-09-01", "2022-09-16"

    border = flow[flow["dimension"] == "border"]
    types = (profile.groupby("scheme_type")
             .agg(schemes=("scheme_id", "size"), avg_transfers=("n_transfers", "mean"),
                  avg_banks=("n_banks", "mean"), avg_countries=("n_countries", "mean"),
                  median_hours=("duration_hours", "median"), median_usd=("total_usd", "median"),
                  in_clean=("share_in_clean", "mean"))
             .reset_index().sort_values("schemes", ascending=False))
    is_true = lambda s: s.astype(str).str.lower() == "true"  # noqa: E731
    bee = bee.assign(entry_eligible=is_true(bee["entry_eligible"]), exit_eligible=is_true(bee["exit_eligible"]))
    for c in ["entries", "exits", "bank_id"]:
        bee[c] = bee[c].astype(int)
    edges = edges.sort_values(["scheme_id", "step"])
    return {
        "kind": "bq2",
        "meta": {"dataset": dataset, "first_day": first_day, "last_day": last_day, "db": db, "source": "athena"},
        "kpi": {"laundering": int(border.loc[border["grp"] == "laundering", "n_tx"].sum()),
                "normal": int(border.loc[border["grp"] == "normal", "n_tx"].sum()),
                "schemes": int(len(profile)),
                "in_clean": int(round((profile["n_transfers"] * profile["share_in_clean"]).sum()))},
        "flow": _records(flow[["grp", "dimension", "value", "n_tx", "share", "usd_median"]]),
        "hold": _records(hold.sort_values(["grp", "bucket_order"])),
        "types": _records(types.round(3)),
        "pairs": _records(pairs.fillna({c: 0 for c in pairs.columns if not c.endswith("country")})),
        "banks": _records(bee),
        "edges": [[int(r.scheme_id), str(r.scheme_type), int(r.step), str(r.ts), str(r.src), str(r.dst),
                   int(r.from_bank), int(r.to_bank), str(r.from_country), str(r.to_country),
                   round(float(r.amount_usd), 2), str(r.payment_format)] for r in edges.itertuples()],
        "profile": _records(profile.assign(entry_banks=profile["entry_banks"].astype(str),
                                           exit_banks=profile["exit_banks"].astype(str))),
        "bankSize": _records(size[["bank_id", "bank_name", "country", "total_txns", "n_accounts"]]
                             .fillna({"total_txns": 0, "n_accounts": 0})
                             .astype({"bank_id": int, "total_txns": int, "n_accounts": int})),
    }


# ---------------------------------------------------------------- BQ1
def _bq1_frames(run: dict | None):
    """(queue, capacity, source, note): Athena first; the CSV export only for the original tables."""
    db = run["db"] if run else None
    if run or os.environ.get("BQ1_DATA_SOURCE", "athena").lower() != "csv":
        try:
            folder = "run" if run else "bq1/dashboard"
            database = db or "aml_curated"
            mock = bool(os.getenv("DASHBOARD_MOCK_DIR"))
            params = {"db": db} if run else {}
            jobs = {n: "" if mock else fill_placeholders(_sql(f"scripts/queries/{folder}/{n}"), params)
                    for n in ("dashboard_queue", "capacity_summary")}
            res = _run_all(jobs, database, f"{ATHENA_OUTPUT}/{folder}", BQ1_TEXT_COLUMNS)
            bad = {n: r for n, r in res.items() if isinstance(r, Exception)}
            if bad:
                raise RuntimeError("; ".join(f"{n}: {str(e)[:200]}" for n, e in bad.items()))
            return bd.prepare_queue(res["dashboard_queue"]), bd.prepare_capacity(res["capacity_summary"]), "athena", ""
        except Exception as err:
            if run:  # the CSV export is HI-Medium, so never show it for another run
                raise
            note = str(err)[:200]
    else:
        note = "BQ1_DATA_SOURCE=csv"
    missing = [f for f in (bd.QUEUE_FILE, bd.CAPACITY_FILE) if not (DATA_DIR / f).exists()]
    if missing:
        raise RuntimeError(f"Athena could not be reached ({note}) and {', '.join(missing)} is missing in {DATA_DIR}.")
    return bd.load_queue(DATA_DIR / bd.QUEUE_FILE), bd.load_capacity(DATA_DIR / bd.CAPACITY_FILE), "csv", note


@st.cache_data(ttl=3600, show_spinner=False)
def bq1_payload(run: dict | None) -> dict:
    """The investigator queue (ranks 1 to 1,000 per date) and the capacity summary, checked by bq1_data."""
    q, cap, source, note = _bq1_frames(run)
    checks = bd.run_checks(q, cap, baseline=run is None)
    q = q.assign(d=q["profile_date"].dt.strftime("%Y-%m-%d"))
    dates = sorted(q["d"].unique())
    di = {d: i for i, d in enumerate(dates)}
    country = q[bd.COUNTRY_COLUMN] if bd.COUNTRY_COLUMN in q else pd.Series("Unknown", index=q.index)
    label = q[bd.LABEL_COLUMN] if bd.LABEL_COLUMN in q else pd.Series(pd.NA, index=q.index)
    active = ({d: _value(g[bd.ACTIVE_COLUMN].iloc[0]) for d, g in q.groupby("d")} if bd.ACTIVE_COLUMN in q
              else {d: None for d in dates})
    points = [c for c, _ in bd.COMPONENTS.values()]
    rows = []
    for r, c, lab in zip(q.itertuples(), country, label):
        rows.append([di[r.d], _value(r.daily_rank), str(r.bank_id), str(r.account_id), str(c),
                     _value(r.risk_score, 4), _value(r.txn_count), _value(r.total_amount_usd, 2),
                     _value(r.ach_share, 4), _value(r.cross_border_share, 4), _value(r.fan_in), _value(r.fan_out),
                     _value(r.amount_band_share, 4), _value(r.pass_through_share_24h, 4),
                     _value(r.activity_spike_ratio, 4)]
                    + [_value(getattr(r, p), 4) for p in points] + [_value(lab) or 0])
    int_cols = {"daily_capacity", "days_evaluated", "total_accounts_reviewed", "total_laundering_detected",
                "total_laundering_account_days"}
    return {
        "kind": "bq1",
        "meta": {"dataset": run["dataset"] if run else "HI-Medium", "db": run["db"] if run else "aml_curated",
                 "source": source, "note": note},
        "bq1": {
            "dates": dates, "active": active, "rows": rows,
            "cap": [{k: (_value(v) if k in int_cols else _value(v, 6)) for k, v in row.items()}
                    for row in cap.to_dict("records")],
            "checks": [[c.name, bool(c.passed), c.detail] for c in checks],
            "total_profiles": bd.TOTAL_PROFILE_ROWS,
        },
    }
