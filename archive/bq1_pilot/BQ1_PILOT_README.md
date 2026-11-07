# BQ1 AML Investigator Dashboard (IS459 Group 7)

A Streamlit dashboard for Business Question 1: *given a fixed daily investigator capacity, which
accounts should be reviewed first, and where should the cut-off be?*

The dashboard is the last stage of the pipeline:

```
Kaggle CSV → S3 raw → Glue Crawler/Catalog → Glue Spark cleaning (Parquet) → S3 clean
→ EMR Serverless Spark (account profiles → risk scoring/ranking/capacity) → S3 curated
→ Athena (validation + investigator queue view) → this Streamlit app
```

It reads only two small exports (up to 16,000 + 5 rows). It never loads the full 14.9 million
ranking rows into Streamlit, holds no AWS credentials and can run locally or on EC2.

## What's inside

| Tab | Shows |
|---|---|
| Daily Investigator Queue | Variable daily capacity of 100, 500 or 1,000; date, country, bank and rank filters; date-aware active-account KPI; hidden-by-default ground-truth evaluation toggle; top 10 by score; value vs score; account explanation; queue table and CSV download |
| Capacity Trade-off | The 100-reviews/day pilot recommendation, a random-review reference point, found/day, precision, detection rate, median cut-off, and the payoff of each step up in capacity |
| Methodology and Limitations | Score components and weights, ranking and label rules, how to add a new date, limitations, and the live data-check results |

The investigator queue displays a neutral grey bank emblem beside each synthetic Bank ID. It is
only a visual aid and does not represent a real financial institution.

## Folder structure

```
bq1-streamlit-dashboard/
├── app.py                  Streamlit app
├── bq1_data.py             Loading, schema checks, validation, display helpers (pandas only)
├── validate.py             Command-line data checks (evidence for the tracker)
├── athena/prepare_dashboard.sql  Country lookup + enriched top-1,000 view
├── requirements.txt
├── .streamlit/config.toml  Theme (navy/teal, light)
├── data/                   Put the two Athena exports here
└── tests/make_sample_data.py   Makes SAMPLE files for testing only
```

## Step 1: Prepare and export the two CSVs from Athena

First run `athena/prepare_dashboard.sql` in sections. It creates:

- `aml_curated.account_country_lookup`, using the account-side country from the clean transactions;
- `aml_curated.bq1_dashboard_queue`, containing ranks 1-1,000, the daily active-account total,
  country and the evaluation-only ground-truth label.

The label is joined only after scores and ranks already exist. The app hides it by default.

Then run each query in Athena, choose **Download results**, and save the file under the exact name shown.

**A. Investigator queue → `data/bq1_investigator_queue.csv`** (expect 16,000 rows: 16 dates × 1,000)

```sql
SELECT *
FROM aml_curated.bq1_dashboard_queue
ORDER BY profile_date, daily_rank;
```

**B. Capacity summary → `data/bq1_capacity_summary.csv`** (expect 5 rows: 50, 100, 500, 1000, 5000)

```sql
SELECT *
FROM aml_curated.capacity_summary
ORDER BY daily_capacity;
```

For each query, record in the evidence tracker: the query execution ID, data scanned, run time,
the result S3 location, and a screenshot.

> Don't open and re-save the CSVs in Excel. Excel can turn IDs like `0025` into `25` or `25.0`.

## Step 2: Check the data

```bash
python validate.py
```

This checks the date coverage, consecutive ranks, score ordering, seven-component total, capacity
figures, label values, daily population consistency and text identifiers. Save the output as evidence.
The same results appear in the app's Methodology tab and in the sidebar.

If a column name is different from what the app expects, it stops and lists the missing and extra
columns. Compare them with the Athena table before renaming anything.

## Step 3: Run the app

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m streamlit run app.py
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m streamlit run app.py
```

The app opens at http://localhost:8501. Once it runs cleanly, pin the exact versions
(`pip freeze | grep -iE "streamlit|pandas|plotly" > requirements.txt`).

### Trying it before the real exports exist

```bash
python tests/make_sample_data.py
BQ1_DATA_DIR=tests/sample_data python -m streamlit run app.py      # PowerShell: $env:BQ1_DATA_DIR="tests/sample_data"
```

The sample queue is **made-up data** with the right columns; never screenshot it as results.
`tests/sample_data/` is git-ignored.

## Evidence to save (handoff section 18)

- [ ] `validate.py` output showing all checks passed
- [ ] Screenshot: latest date (16 Sep 2022) queue tab
- [ ] Screenshot: a different date selected
- [ ] Screenshot: capacity changed from 100 to 1,000
- [ ] Screenshot: country filter applied
- [ ] Screenshot: ground truth hidden, then enabled in evaluation mode
- [ ] Screenshot: Capacity Trade-off tab
- [ ] Final source code + pinned `requirements.txt`

## Rules this app keeps

- Uses only the two curated exports; never loads the raw data or all 14.9M rankings in Streamlit.
- `bank_id`, `account_id` and `account_key` are text, never summed or averaged.
- Ground truth is hidden by default and clearly marked as evaluation-only when enabled.
- The queue is the top N ranks for the selected date; a permanent score threshold is not used.
- `account_country` is the account-side country from the transaction data, not a verified bank-HQ location.
- A high score means *review first*, not *proven laundering*.
- No AWS keys in code or Git. If a live Athena connection is added later, use an IAM role.
