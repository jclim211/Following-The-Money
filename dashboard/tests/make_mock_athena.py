"""Make MOCK Athena result CSVs so the UI can be run and screenshotted without AWS.

Numbers are random and only shaped like the real outputs. Never present them as results.

Usage:  python tests/make_mock_athena.py            -> writes tests/mock_athena/
        DASHBOARD_MOCK_DIR=tests/mock_athena BQ1_DATA_SOURCE=csv streamlit run Home.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "mock_athena"
rng = np.random.default_rng(7)
COUNTRIES = ["US", "UK", "Germany", "France", "Italy", "Spain", "Netherlands", "Switzerland", "Japan", "China",
             "Brazil", "Mexico", "India", "Canada", "Australia", "Crypto"]
NAMES = ["First Bank", "Future Savings Bank", "Harbor Trust", "Northwind Bank", "Bank of Pine", "Atlas Credit",
         "Meridian Bank", "Granite Savings", "Bluewater Bank", "Summit Bank", "Oak Union", "Cedar Capital",
         "Coastal Bank", "Pioneer Trust", "Silverline Bank", "Keystone Bank"]


def bq2():
    out = OUT / "bq2" / "dashboard"
    out.mkdir(parents=True, exist_ok=True)
    banks = pd.DataFrame({"bank_id": rng.choice(np.arange(10, 30000), 120, replace=False)})
    banks["bank_name"] = [f"{NAMES[i % len(NAMES)]}" + (f" #{i // len(NAMES)}" if i >= len(NAMES) else "")
                          for i in range(len(banks))]
    banks["country"] = rng.choice(COUNTRIES, len(banks), p=np.r_[[0.2, 0.12], [0.68 / 14] * 14])
    banks["total_txns"] = (np.exp(rng.normal(9, 1.5, len(banks)))).astype(int) + 50
    banks["n_accounts"] = (banks["total_txns"] / rng.uniform(3, 9, len(banks))).astype(int) + 5
    banks.to_csv(out / "bank_size.csv", index=False)
    weight = banks["total_txns"] / banks["total_txns"].sum()
    hot = rng.choice(banks.index, 8, replace=False)
    w = weight.copy()
    w[hot] *= 8
    w /= w.sum()
    country = dict(zip(banks["bank_id"], banks["country"]))

    def acc():
        b = int(banks["bank_id"].iloc[rng.choice(len(banks), p=w)])
        return f"{b}:{rng.integers(0x10000000, 0xFFFFFFFF):X}"

    types = ["FAN-OUT", "FAN-IN", "GATHER-SCATTER", "SCATTER-GATHER", "CYCLE", "RANDOM", "BIPARTITE", "STACK"]
    rows, sid = [], 0
    for t in types:
        for _ in range(rng.integers(25, 60)):
            sid += 1
            k = int(rng.integers(3, 9))
            if t == "FAN-OUT":
                a = acc(); pairs = [(a, acc()) for _ in range(k)]
            elif t == "FAN-IN":
                z = acc(); pairs = [(acc(), z) for _ in range(k)]
            elif t == "GATHER-SCATTER":
                h = acc(); pairs = [(acc(), h) for _ in range(k)] + [(h, acc()) for _ in range(k)]
            elif t == "SCATTER-GATHER":
                a, z = acc(), acc(); mids = [acc() for _ in range(k)]
                pairs = [(a, m) for m in mids] + [(m, z) for m in mids]
            elif t == "CYCLE":
                chain = [acc() for _ in range(k)]; pairs = list(zip(chain, chain[1:] + chain[:1]))
            elif t == "RANDOM":
                chain = [acc() for _ in range(k)]; pairs = list(zip(chain, chain[1:]))
            elif t == "BIPARTITE":
                s, r = [acc() for _ in range(3)], [acc() for _ in range(3)]
                pairs = [(x, y) for x in s for y in r if rng.random() < 0.7]
            else:
                s, m, r = [acc() for _ in range(3)], [acc() for _ in range(3)], [acc() for _ in range(3)]
                pairs = [(x, y) for x in s for y in m if rng.random() < .6] + \
                        [(x, y) for x in m for y in r if rng.random() < .6]
            start = pd.Timestamp("2022-09-01") + pd.Timedelta(minutes=int(rng.integers(0, 14 * 1440)))
            ts = start
            for step, (a, b) in enumerate(pairs):
                ts = ts + pd.Timedelta(minutes=int(rng.integers(5, 600)))
                fa, fb = int(a.split(":")[0]), int(b.split(":")[0])
                rows.append(dict(scheme_id=sid, scheme_type=t, step=step, ts=ts.strftime("%Y-%m-%d %H:%M:%S"),
                                 src=a, dst=b, from_bank=fa, to_bank=fb, from_country=country[fa],
                                 to_country=country[fb], amount_usd=round(float(np.exp(rng.normal(9, 1.2))), 2),
                                 payment_format=rng.choice(["ACH", "Cheque", "Credit Card", "Wire", "Cash",
                                                            "Bitcoin"], p=[.6, .12, .1, .1, .05, .03])))
    e = pd.DataFrame(rows)
    e.to_csv(out / "scheme_edges.csv", index=False)

    prof = []
    for sid, g in e.groupby("scheme_id"):
        outs, ins = set(g["src"]), set(g["dst"])
        en, ex = outs - ins or {g.iloc[0]["src"]}, ins - outs or {g.iloc[-1]["dst"]}
        accs = outs | ins
        bks = set(g["from_bank"]) | set(g["to_bank"])
        prof.append(dict(scheme_id=sid, scheme_type=g["scheme_type"].iloc[0], n_transfers=len(g),
                         n_accounts=len(accs), n_banks=len(bks),
                         n_countries=len(set(g["from_country"]) | set(g["to_country"])),
                         duration_hours=(pd.to_datetime(g["ts"]).max() - pd.to_datetime(g["ts"]).min())
                         .total_seconds() / 3600, total_usd=g["amount_usd"].sum(),
                         share_in_clean=round(float(rng.uniform(0.8, 1)), 3),
                         entry_banks=",".join(sorted({a.split(":")[0] for a in en})),
                         exit_banks=",".join(sorted({a.split(":")[0] for a in ex}))))
    prof = pd.DataFrame(prof)
    prof.to_csv(out / "scheme_profile.csv", index=False)

    ent = prof.assign(b=prof["entry_banks"].str.split(",")).explode("b")["b"].astype(int).value_counts()
    ext = prof.assign(b=prof["exit_banks"].str.split(",")).explode("b")["b"].astype(int).value_counts()
    bee = banks[["bank_id", "bank_name", "country"]].copy()
    bee["entries"] = bee["bank_id"].map(ent).fillna(0).astype(int)
    bee["exits"] = bee["bank_id"].map(ext).fillna(0).astype(int)
    bee["expected_entries"] = ent.sum() * weight
    bee["expected_exits"] = ext.sum() * weight
    bee["entry_ratio"] = bee["entries"] / bee["expected_entries"]
    bee["exit_ratio"] = bee["exits"] / bee["expected_exits"]
    bee["entry_eligible"] = bee["entries"] >= 5
    bee["exit_eligible"] = bee["exits"] >= 5
    bee.to_csv(out / "bank_entry_exit.csv", index=False)

    fl = []
    for dim, vals in {"payment_format": ["ACH", "Cheque", "Credit Card", "Wire", "Cash", "Bitcoin", "Reinvestment"],
                      "border": ["domestic", "cross-border"], "conversion": ["same currency", "converted"]}.items():
        for grp, n in [("laundering", 52_000), ("normal", 31_000_000)]:
            sh = rng.dirichlet(np.ones(len(vals)) * (0.6 if grp == "laundering" else 2))
            for v, s_ in zip(vals, sh):
                fl.append(dict(grp=grp, dimension=dim, value=v, n_tx=int(n * s_), share=s_,
                               usd_median=float(np.exp(rng.normal(8, 1)))))
    pd.DataFrame(fl).to_csv(out / "flow_comparison.csv", index=False)

    buckets = ["< 1 h", "1-6 h", "6-24 h", "1-3 d", "> 3 d", "never"]
    ho = []
    for grp, med in [("laundering", 827), ("normal", 721)]:
        sh = rng.dirichlet(np.ones(len(buckets)) * 2)
        for i, (b, s_) in enumerate(zip(buckets, sh)):
            ho.append(dict(grp=grp, bucket=b, bucket_order=i, n=int(s_ * 1e5), share=s_, median_hold_minutes=med))
    pd.DataFrame(ho).to_csv(out / "holding_time.csv", index=False)

    cp = []
    for a in COUNTRIES:
        for b in COUNTRIES:
            nl = int(np.exp(rng.normal(3 if a != b else 6, 1.5)))
            nn = int(nl * rng.uniform(300, 3000))
            cp.append(dict(from_country=a, to_country=b, n_laundering=nl, n_normal=nn))
    cp = pd.DataFrame(cp)
    cp["laundering_rate"] = cp["n_laundering"] / (cp["n_laundering"] + cp["n_normal"])
    cp["share_of_laundering"] = cp["n_laundering"] / cp["n_laundering"].sum()
    cp.to_csv(out / "country_pairs.csv", index=False)


def bq1():
    out = OUT / "bq1" / "dashboard"
    out.mkdir(parents=True, exist_ok=True)
    q = pd.read_csv(Path(__file__).parents[1] / "data_bq1" / "bq1_investigator_queue.csv",
                    dtype={"bank_id": str, "account_id": str, "account_key": str, "profile_date": str})
    days = sorted(q["profile_date"].unique())
    pd.DataFrame({"profile_date": days}).to_csv(out / "available_dates.csv", index=False)
    day = q[q["profile_date"] == days[-1]].rename(columns={"account_day_is_laundering": "is_laundering"})
    day.head(100).to_csv(out / "queue_top_accounts.csv", index=False)
    pd.DataFrame({"account_key": day["account_key"].head(30), "prior_flag_days": rng.integers(1, 5, 30),
                  "first_flagged": days[0]}).to_csv(out / "queue_prior_flag_days.csv", index=False)
    pd.DataFrame({"t": [3104]}).to_csv(out / "kpi_day_laundering_total.csv", index=False)
    pd.DataFrame({"t": [49665]}).to_csv(out / "kpi_period_laundering_total.csv", index=False)
    nv = pd.DataFrame({"profile_date": days, "new_accounts": rng.integers(40, 90, len(days))})
    nv["repeat_accounts"] = 100 - nv["new_accounts"]
    nv["new_laundering"] = rng.integers(5, 30, len(days))
    nv["repeat_laundering"] = rng.integers(5, 30, len(days))
    nv.to_csv(out / "queue_new_vs_repeat.csv", index=False)
    caps = np.arange(50, 1050, 50)
    pd.DataFrame({"daily_capacity": caps, "caught_score": (300 * np.log1p(caps / 40)).astype(int),
                  "caught_baseline": (120 * np.log1p(caps / 40)).astype(int)}).to_csv(
        out / "capacity_vs_baseline.csv", index=False)
    pd.read_csv(Path(__file__).parents[1] / "data_bq1" / "bq1_capacity_summary.csv").to_csv(
        out / "capacity_summary.csv", index=False)
    bins = np.arange(0, 100, 2.5)
    sd = pd.concat([pd.DataFrame({"score_bin": bins, "is_laundering": 0,
                                  "accounts": (1e5 * np.exp(-((bins - 35) / 15) ** 2)).astype(int) + 1}),
                    pd.DataFrame({"score_bin": bins, "is_laundering": 1,
                                  "accounts": (300 * np.exp(-((bins - 60) / 12) ** 2)).astype(int) + 1})])
    sd.to_csv(out / "score_distribution.csv", index=False)
    acc = day.iloc[0]
    h = q[q["account_key"] == acc["account_key"]].rename(columns={"account_day_is_laundering": "is_laundering"})
    if h.empty:
        h = day.head(1)
    h.to_csv(out / "account_score_history.csv", index=False)
    p = day.head(1).assign(incoming_txn_count=2, outgoing_txn_count=3, incoming_amount_usd=1200.0,
                           outgoing_amount_usd=1150.0)
    p.to_csv(out / "account_profile_detail.csv", index=False)
    (OUT / "bq1" / "analysis").mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    bq2()
    bq1()
    print(f"MOCK data written to {OUT}")
