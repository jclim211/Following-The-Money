"""Data loading, validation and display helpers for the BQ1 dashboard.

Pure pandas, no Streamlit import, so it can be tested and run from the command
line (see validate.py). The business logic (scores, ranks, capacity results)
is produced upstream on AWS; this module only reads, checks and summarises it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# File names and expected schema (from the BQ1 handoff, sections 11-12)
# ---------------------------------------------------------------------------
QUEUE_FILE = "bq1_investigator_queue.csv"
CAPACITY_FILE = "bq1_capacity_summary.csv"

ID_COLUMNS = ["bank_id", "account_id", "account_key"]
INT_COLUMNS = ["daily_rank", "txn_count", "fan_in", "fan_out"]
SHARE_COLUMNS = ["ach_share", "cross_border_share", "amount_band_share", "pass_through_share_24h"]

# Display name -> (points column, maximum points). Order = order shown in charts.
COMPONENTS = {
    "ACH share": ("ach_points", 25),
    "Cross-border share": ("cross_border_points", 15),
    "Fan-out": ("fan_out_points", 15),
    "Fan-in": ("fan_in_points", 15),
    "Amount band": ("amount_band_points", 10),
    "Pass-through (24h)": ("pass_through_points", 10),
    "Activity spike": ("activity_spike_points", 10),
}
POINT_COLUMNS = [col for col, _ in COMPONENTS.values()]

MEASURE_COLUMNS = (
    ["risk_score", "total_amount_usd"]
    + SHARE_COLUMNS
    + ["activity_spike_ratio"]
    + POINT_COLUMNS
)

QUEUE_COLUMNS = ["profile_date"] + ["daily_rank"] + ID_COLUMNS + [
    "risk_score", "txn_count", "total_amount_usd", "ach_share", "cross_border_share",
    "fan_in", "fan_out", "amount_band_share", "pass_through_share_24h",
    "activity_spike_ratio",
] + POINT_COLUMNS

CAPACITY_COLUMNS = [
    "daily_capacity", "days_evaluated", "avg_accounts_reviewed_per_day",
    "avg_laundering_detected_per_day", "recommended_score_threshold",
    "overall_precision", "overall_detection_rate",
]

OPTIONAL_CAPACITY_COLUMNS = [
    "total_accounts_reviewed", "total_laundering_detected", "total_laundering_account_days",
    "min_daily_cutoff_score", "max_daily_cutoff_score",
]

# Columns that must never appear in the operational queue (target leakage).
LABEL_COLUMNS = {"is_laundering", "account_day_is_laundering", "label", "y"}

# ---------------------------------------------------------------------------
# Verified figures from the handoff (sections 9-10). Used only for validation.
# If the pipeline is rerun with more dates, update these and say so in the README.
# ---------------------------------------------------------------------------
EXPECTED_DATES = 16
EXPECTED_ROWS_PER_DATE = 100
EXPECTED_LATEST_DATE = pd.Timestamp("2022-09-16")
TOTAL_PROFILE_ROWS = 14_887_977  # all account-day profiles scored upstream
RECOMMENDED_CAPACITY = 100

VERIFIED_CAPACITY = pd.DataFrame(
    {
        "daily_capacity": [50, 100, 500, 1000, 5000],
        "avg_laundering_detected_per_day": [18.1875, 34.75, 99.625, 142.125, 399.8125],
        "recommended_score_threshold": [75.0, 72.5, 67.5, 67.5, 59.4444],
        "overall_precision": [0.36375, 0.3475, 0.19925, 0.142125, 0.0799625],
        "overall_detection_rate": [0.005859, 0.011195, 0.032095, 0.045787, 0.128803],
    }
)


class SchemaError(ValueError):
    """Raised when an exported CSV does not match the expected Athena schema."""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _check_columns(df: pd.DataFrame, expected: list[str], name: str) -> None:
    missing = [c for c in expected if c not in df.columns]
    if missing:
        extra = [c for c in df.columns if c not in expected]
        raise SchemaError(
            f"{name} is missing columns {missing}. Columns found that were not expected: "
            f"{extra or 'none'}. Compare the CSV header with the Athena table before renaming "
            "anything (handoff section 24)."
        )


def _to_numeric(df: pd.DataFrame, cols: list[str], name: str) -> None:
    """Convert to numbers; fail loudly if a non-blank value is not a number."""
    for col in cols:
        raw = df[col]
        converted = pd.to_numeric(raw, errors="coerce")
        blank = raw.isna() | raw.astype("string").str.strip().eq("")
        bad = converted.isna() & ~blank
        if bad.any():
            sample = raw[bad].astype(str).head(3).tolist()
            raise SchemaError(f"{name}: column '{col}' has non-numeric values, e.g. {sample}")
        df[col] = converted


def load_queue(path: str | Path) -> pd.DataFrame:
    """Load the 1,600-row investigator queue export."""
    df = pd.read_csv(path, dtype={c: "string" for c in ID_COLUMNS})
    _check_columns(df, QUEUE_COLUMNS, "Queue CSV")
    for col in ID_COLUMNS:
        df[col] = df[col].str.strip()
    df["profile_date"] = pd.to_datetime(df["profile_date"], errors="raise").dt.normalize()
    _to_numeric(df, INT_COLUMNS + MEASURE_COLUMNS, "Queue CSV")
    for col in INT_COLUMNS:
        if (df[col].dropna() % 1 != 0).any():
            raise SchemaError(f"Queue CSV: column '{col}' should hold whole numbers")
        df[col] = df[col].astype("Int64")
    return df.sort_values(["profile_date", "daily_rank"]).reset_index(drop=True)


def load_capacity(path: str | Path) -> pd.DataFrame:
    """Load the 5-row capacity summary export."""
    df = pd.read_csv(path)
    _check_columns(df, CAPACITY_COLUMNS, "Capacity CSV")
    # The real export also carries totals and min/max daily cut-offs; use them when present.
    _to_numeric(df, CAPACITY_COLUMNS + [c for c in OPTIONAL_CAPACITY_COLUMNS if c in df.columns], "Capacity CSV")
    df["daily_capacity"] = df["daily_capacity"].astype("Int64")
    df["days_evaluated"] = df["days_evaluated"].astype("Int64")
    return df.sort_values("daily_capacity").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Validation (handoff section 18, data checks)
# ---------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    passed: bool
    detail: str


def run_checks(queue: pd.DataFrame, capacity: pd.DataFrame) -> list[Check]:
    checks: list[Check] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append(Check(name, bool(passed), detail))

    n_dates = queue["profile_date"].nunique()
    per_date = queue.groupby("profile_date").size()

    add("Queue has 1,600 rows", len(queue) == EXPECTED_DATES * EXPECTED_ROWS_PER_DATE,
        f"{len(queue):,} rows")
    add("Capacity summary has 5 rows", len(capacity) == 5, f"{len(capacity)} rows")
    add("Queue covers 16 dates", n_dates == EXPECTED_DATES, f"{n_dates} dates")
    add("Every date has exactly 100 rows", bool((per_date == EXPECTED_ROWS_PER_DATE).all()),
        f"min {per_date.min()}, max {per_date.max()} rows per date")

    ranks_ok = queue.groupby("profile_date")["daily_rank"].apply(
        lambda r: sorted(r.dropna().astype(int).tolist()) == list(range(1, EXPECTED_ROWS_PER_DATE + 1))
    )
    bad_dates = [d.date().isoformat() for d, ok in ranks_ok.items() if not ok]
    add("Every date has unique ranks 1-100", ranks_ok.all(),
        "all dates OK" if not bad_dates else f"problem dates: {bad_dates[:5]}")

    latest = queue["profile_date"].max()
    add("Latest (default) date is 2022-09-16", latest == EXPECTED_LATEST_DATE,
        f"latest date in file: {latest.date().isoformat()}")

    ordered = queue.sort_values(["profile_date", "daily_rank"])
    rises = ordered.groupby("profile_date")["risk_score"].diff().gt(1e-9).sum()
    add("Risk score never rises as rank gets worse", rises == 0,
        f"{int(rises)} rank steps where the score went up")

    diff = (queue[POINT_COLUMNS].fillna(0).sum(axis=1) - queue["risk_score"]).abs()
    add("Seven components add up to risk_score (within 0.01)", (diff <= 0.01).all(),
        f"largest gap {diff.max():.4f}")

    merged = VERIFIED_CAPACITY.merge(capacity, on="daily_capacity", how="left", suffixes=("_exp", ""))
    mismatches = []
    for col in ["avg_laundering_detected_per_day", "recommended_score_threshold",
                "overall_precision", "overall_detection_rate"]:
        for _, row in merged.iterrows():
            exp, got = row[f"{col}_exp"], row[col]
            if pd.isna(got) or not math.isclose(exp, got, rel_tol=1e-3, abs_tol=1e-5):
                mismatches.append(f"{int(row['daily_capacity'])}/{col}: expected {exp}, got {got}")
    add("Capacity figures match the verified results", not mismatches,
        "all 5 capacities match" if not mismatches else "; ".join(mismatches[:3]))

    leaked = sorted(LABEL_COLUMNS.intersection(queue.columns))
    add("No ground-truth label in the queue", not leaked,
        "no label column" if not leaked else f"found {leaked}")

    bad_ids = queue[ID_COLUMNS].apply(lambda s: s.str.fullmatch(r".*\.0").fillna(False)).any(axis=None)
    add("Identifiers kept as text (no '.0' suffix)", not bad_ids,
        "bank_id, account_id, account_key are text")
    return checks


# ---------------------------------------------------------------------------
# Derived figures for the UI (display helpers only; source data untouched)
# ---------------------------------------------------------------------------
def day_kpis(selected: pd.DataFrame) -> dict:
    return {
        "queue_size": len(selected),
        "highest": selected["risk_score"].max(),
        "average": selected["risk_score"].mean(),
        "cutoff": selected["risk_score"].min(),
        "value": selected["total_amount_usd"].sum(),
    }


def component_table(row: pd.Series) -> pd.DataFrame:
    """Points earned vs maximum for one account-day, in fixed component order."""
    out = []
    for label, (col, max_pts) in COMPONENTS.items():
        pts = row[col]
        out.append({"component": label, "points": 0.0 if pd.isna(pts) else float(pts), "max_points": max_pts})
    return pd.DataFrame(out)


def average_components(selected: pd.DataFrame) -> pd.DataFrame:
    out = []
    for label, (col, max_pts) in COMPONENTS.items():
        out.append({"component": label, "points": selected[col].fillna(0).mean(), "max_points": max_pts})
    return pd.DataFrame(out)


def _pct(x) -> str:
    return "N/A" if pd.isna(x) else f"{x:.0%}"


def _describe(label: str, row: pd.Series) -> str:
    if label == "ACH share":
        return f"{_pct(row['ach_share'])} of its activity used ACH"
    if label == "Cross-border share":
        if pd.isna(row["cross_border_share"]):
            return "cross-border share is not available for this account-day"
        return f"{_pct(row['cross_border_share'])} of its activity crossed countries"
    if label == "Fan-out":
        return f"it sent money to {int(row['fan_out'])} different accounts"
    if label == "Fan-in":
        return f"it received money from {int(row['fan_in'])} different accounts"
    if label == "Amount band":
        return f"{_pct(row['amount_band_share'])} of its activity sat in the day's mid-to-high amount band"
    if label == "Pass-through (24h)":
        return f"{_pct(row['pass_through_share_24h'])} of the money it sent out left within 24 hours of money arriving"
    if label == "Activity spike":
        return f"it made {row['activity_spike_ratio']:.1f}x its usual number of transactions"
    return label


def explain(row: pd.Series) -> str:
    """One or two plain-English sentences on why an account-day ranks where it does."""
    comps = component_table(row)
    comps["fill"] = comps["points"] / comps["max_points"]
    top = comps[comps["points"] > 0].sort_values(["points", "fill"], ascending=False).head(3)
    date_txt = row["profile_date"].strftime("%d %b %Y")
    first = (
        f"Account {row['account_key']} is rank {int(row['daily_rank'])} on {date_txt} "
        f"with a risk score of {row['risk_score']:.2f} out of 100."
    )
    if top.empty:
        return first
    def join(items: list[str], sep: str) -> str:
        return items[0] if len(items) == 1 else sep.join(items[:-1]) + " and " + items[-1]

    parts = [f"{r.component} ({r.points:g}/{r.max_points})" for r in top.itertuples()]
    reasons = [_describe(r.component, row) for r in top.itertuples()]
    return f"{first} Most of the score comes from {join(parts, ', ')}: {join(reasons, '; ')}."


def capacity_view(capacity: pd.DataFrame) -> pd.DataFrame:
    """Capacity table plus the marginal yield of each step up in capacity."""
    cap = capacity.copy()
    cap["label"] = cap["daily_capacity"].map(lambda c: f"{int(c):,}")
    cap["extra_reviews"] = cap["avg_accounts_reviewed_per_day"].diff()
    cap["extra_found"] = cap["avg_laundering_detected_per_day"].diff()
    cap["found_per_extra_review"] = cap["extra_found"] / cap["extra_reviews"]
    cap["step"] = cap["label"].shift() + " → " + cap["label"]  # first row stays blank
    return cap


def random_review_reference(capacity: pd.DataFrame) -> dict:
    """What reviewing randomly chosen active accounts would find, for context.

    laundering account-days per day = detected per day / detection rate
    active account-days per day     = all scored profiles / days evaluated
    """
    row = capacity.loc[capacity["daily_capacity"] == RECOMMENDED_CAPACITY].iloc[0]
    if "total_laundering_account_days" in capacity.columns:  # present in the real export
        laundering_per_day = row["total_laundering_account_days"] / int(row["days_evaluated"])
    else:
        laundering_per_day = row["avg_laundering_detected_per_day"] / row["overall_detection_rate"]
    active_per_day = TOTAL_PROFILE_ROWS / int(row["days_evaluated"])
    base_rate = laundering_per_day / active_per_day
    return {
        "laundering_per_day": laundering_per_day,
        "active_per_day": active_per_day,
        "base_rate": base_rate,
        "lift": row["overall_precision"] / base_rate,
    }
