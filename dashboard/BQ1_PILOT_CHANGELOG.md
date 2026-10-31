# BQ1 merged dashboard changes

## v2.1

- Added a neutral grey bank icon to every investigator-queue row.
- Kept the Bank ID visible and avoided real logos because the source bank IDs are synthetic.

## Added

- Date-aware **Active accounts on [selected date]** KPI.
- Daily investigator-capacity selector for **100, 500 and 1,000** accounts.
- **Show ground truth** evaluation toggle, hidden by default.
- Country filter followed by bank-ID filter.
- Ground-truth status in the account explanation and ranking table only when enabled.
- Existing **Top 10 accounts by risk score**, risk/value scatter and score explanation retained.
- Dynamic CSV downloads that exclude the ground-truth label while evaluation mode is off.
- Athena SQL to create the account-country lookup and enriched top-1,000 dashboard view.

## Data requirements

The enriched queue export should contain:

- ranks 1-1,000 for every date;
- `daily_active_accounts`;
- `account_country`;
- `account_day_is_laundering`.

The application remains compatible with the original top-100 export, but controls that depend on
missing columns are hidden and a warning explains what must be added.

## Safety rule

Ground truth is joined after scoring and ranking and is hidden by default. It is for retrospective
evaluation and demonstrations only, not information an investigator would possess before review.

