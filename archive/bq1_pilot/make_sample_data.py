"""Make SAMPLE CSVs with the enriched top-1,000 dashboard schema.

For testing the app before the real exports exist. The queue numbers are made up
(random accounts scored with the documented point rules); the capacity file copies
the verified figures from the handoff. Never present this sample as real results.

Usage:  python tests/make_sample_data.py      -> writes tests/sample_data/
        BQ1_DATA_DIR=tests/sample_data python -m streamlit run app.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bq1_data as bd  # noqa: E402

OUT = Path(__file__).parent / "sample_data"
rng = np.random.default_rng(459)


def one_day(date: pd.Timestamp, pool: int = 5000) -> pd.DataFrame:
    n = pool
    df = pd.DataFrame({
        "bank_id": rng.choice([str(b) for b in [1, 11, 12, 25, 70, 119, 1124, 21174, 220, 3402]], n),
        "account_id": [f"{rng.integers(0x100000000, 0xFFFFFFFFF):X}" for _ in range(n)],
        "txn_count": rng.integers(1, 12, n),
        "total_amount_usd": np.round(np.exp(rng.normal(9.5, 1.6, n)), 2),
        "ach_share": np.clip(rng.beta(3, 1.2, n).round(2), 0, 1),
        "cross_border_share": np.where(rng.random(n) < 0.05, np.nan, rng.beta(2, 1.5, n).round(2)),
        "fan_in": rng.integers(0, 7, n),
        "fan_out": rng.integers(0, 7, n),
        "amount_band_share": rng.beta(2, 1.3, n).round(2),
        "pass_through_share_24h": rng.beta(1.5, 1.5, n).round(2),
        "activity_spike_ratio": np.round(np.exp(rng.normal(0.4, 0.6, n)), 4),
    })
    df["account_key"] = df["bank_id"] + ":" + df["account_id"]
    bank_country = {
        "1": "United States", "11": "United Kingdom", "12": "Singapore",
        "25": "Japan", "70": "Germany", "119": "Canada", "1124": "Australia",
        "21174": "Netherlands", "220": "France", "3402": "Hong Kong",
    }
    df[bd.COUNTRY_COLUMN] = df["bank_id"].map(bank_country).fillna("Unknown")
    p95_fan, p95_spike = 4, 3.5
    df["ach_points"] = 25 * df["ach_share"]
    df["cross_border_points"] = 15 * df["cross_border_share"].fillna(0)
    df["fan_out_points"] = 15 * np.minimum(df["fan_out"] / p95_fan, 1)
    df["fan_in_points"] = 15 * np.minimum(df["fan_in"] / p95_fan, 1)
    df["amount_band_points"] = 10 * df["amount_band_share"]
    df["pass_through_points"] = 10 * df["pass_through_share_24h"]
    df["activity_spike_points"] = 10 * np.minimum(df["activity_spike_ratio"] / p95_spike, 1)
    df[bd.POINT_COLUMNS] = df[bd.POINT_COLUMNS].round(4)
    df["risk_score"] = df[bd.POINT_COLUMNS].sum(axis=1).round(4)
    df = df.sort_values(["risk_score", "total_amount_usd", "account_key"],
                        ascending=[False, False, True]).head(1000)
    df["daily_rank"] = range(1, len(df) + 1)
    df["profile_date"] = date.date().isoformat()
    df[bd.ACTIVE_COLUMN] = int(rng.integers(850_000, 1_450_000))
    # Evaluation-only sample label. It is hidden by default in the app.
    hit_probability = np.clip((df["risk_score"] - 50) / 100, 0.02, 0.55)
    df[bd.LABEL_COLUMN] = (rng.random(len(df)) < hit_probability).astype(int)
    return df[bd.QUEUE_COLUMNS + bd.OPTIONAL_QUEUE_COLUMNS]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2022-09-01", "2022-09-16", freq="D")
    queue = pd.concat([one_day(d) for d in dates], ignore_index=True)
    queue.to_csv(OUT / bd.QUEUE_FILE, index=False)

    cap = bd.VERIFIED_CAPACITY.copy()
    cap["days_evaluated"] = 16
    cap["avg_accounts_reviewed_per_day"] = cap["daily_capacity"].astype(float)
    cap[bd.CAPACITY_COLUMNS].to_csv(OUT / bd.CAPACITY_FILE, index=False)
    print(f"SAMPLE data written to {OUT} ({len(queue)} queue rows, {len(cap)} capacity rows)")


if __name__ == "__main__":
    main()
