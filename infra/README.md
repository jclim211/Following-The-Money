# Infra (Terraform)

Lets the dashboard start pipeline runs. Runs no longer start on upload.

| Resource | What Terraform does |
|---|---|
| State machine `is459-g7-pipeline` | Imported. Definition comes from `pipeline/orchestration/is459-g7-pipeline.asl.json`, so a change to that file is deployed with `terraform apply`. |
| Its IAM role | Imported, with `pipeline/orchestration/pipeline-role-policy.json` as an inline policy. |
| EventBridge upload trigger | Imported and set to **DISABLED**. The Lambda (`trigger.py`) stays but is no longer called. |
| Dashboard role `is459-g7-dashboard-role` | New inline policy `is459-g7-dashboard-pipeline`: list `runs/`, read `run.json`, list and start executions of the pipeline. The existing policies on the role are left alone. |

State: `s3://is459-g7-projectbucket/tfstate/pipeline.tfstate`.

## Apply (Mac or Windows, once per change)

Needs Terraform 1.10+ and AWS CLI v2, signed in as in `context.md` (`aws login --profile is459 --region us-east-1`).

```
cd infra
export AWS_PROFILE=is459                        # Windows: set AWS_PROFILE=is459
terraform init
terraform plan -out tfplan                      # read it: imports, 1 new policy, rule -> DISABLED
terraform apply tfplan
```

The resource names are the defaults in `variables.tf` (checked in AWS on 7 Nov). To check them again:

```
aws stepfunctions describe-state-machine --state-machine-arn arn:aws:states:us-east-1:761018854594:stateMachine:is459-g7-pipeline --query roleArn
aws events list-rules --name-prefix is459 --query "Rules[].[Name,State]"
```

The pipeline role's inline policy `is459-g7-pipeline-policy` is imported too, so the plan shows any difference between it and `pipeline/orchestration/pipeline-role-policy.json`.

## Passcode for the Start button

The Start button stays off until the server has a passcode. On the EC2 server (Session Manager):

```
sudo mkdir -p /opt/bq1/repo/dashboard/.streamlit
echo 'pipeline_passcode = "<choose one>"' | sudo tee /opt/bq1/repo/dashboard/.streamlit/secrets.toml
sudo systemctl restart bq1-dashboard
```

`secrets.toml` is git-ignored, so deploys keep it. Locally, put the same line in `dashboard/.streamlit/secrets.toml` or set `PIPELINE_PASSCODE`.

## Upload a run

```
aws s3 cp HI-Small_Trans.csv     s3://is459-g7-projectbucket/runs/hi-small-4/raw/transactions/
aws s3 cp HI-Small_Patterns.txt  s3://is459-g7-projectbucket/runs/hi-small-4/raw/patterns/
aws s3 cp HI-Small_accounts.csv  s3://is459-g7-projectbucket/runs/hi-small-4/raw/accounts/
```

Run names: lowercase letters, numbers and hyphens. The home page shows the run as "Ready to start" once all three files are there.
