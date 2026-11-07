# Run the pipeline from the dashboard.
#
# The state machine, its role and the upload trigger were first made by hand. The import
# blocks below bring them under Terraform on the first apply; nothing is recreated.
# New here: an extra inline policy on the dashboard server's role, so its Start button can
# list uploads and start executions, and the upload trigger is switched off.

locals {
  pipeline_arn = "arn:aws:states:${var.region}:${var.account_id}:stateMachine:${var.state_machine_name}"
}

# ---------- the pipeline ----------

import {
  to = aws_iam_role.pipeline
  id = var.pipeline_role_name
}

resource "aws_iam_role" "pipeline" {
  name               = var.pipeline_role_name
  assume_role_policy = file("${path.module}/../pipeline/orchestration/pipeline-role-trust.json")
}

import {
  to = aws_iam_role_policy.pipeline
  id = "${var.pipeline_role_name}:is459-g7-pipeline-policy"
}

resource "aws_iam_role_policy" "pipeline" {
  name   = "is459-g7-pipeline-policy"
  role   = aws_iam_role.pipeline.name
  policy = file("${path.module}/../pipeline/orchestration/pipeline-role-policy.json")
}

import {
  to = aws_sfn_state_machine.pipeline
  id = local.pipeline_arn
}

resource "aws_sfn_state_machine" "pipeline" {
  name       = var.state_machine_name
  role_arn   = aws_iam_role.pipeline.arn
  definition = file("${path.module}/../pipeline/orchestration/is459-g7-pipeline.asl.json")
}

# ---------- runs start from the dashboard only ----------

import {
  to = aws_cloudwatch_event_rule.upload_trigger
  id = var.trigger_rule_name
}

resource "aws_cloudwatch_event_rule" "upload_trigger" {
  name          = var.trigger_rule_name
  description   = "Started is459-g7-pipeline on upload. Disabled: runs start from the dashboard."
  event_pattern = file("${path.module}/../pipeline/orchestration/trigger-event-pattern.json")
  state         = "DISABLED"
}

# ---------- the dashboard server may list uploads and start runs ----------

resource "aws_iam_role_policy" "dashboard_pipeline" {
  name = "is459-g7-dashboard-pipeline"
  role = var.dashboard_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "ListRunFolders"
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = "arn:aws:s3:::${var.bucket}"
        Condition = { StringLike = { "s3:prefix" = ["runs/*"] } }
      },
      {
        Sid      = "ReadRunRecords"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "arn:aws:s3:::${var.bucket}/runs/*/run.json"
      },
      {
        Sid      = "StartAndWatchRuns"
        Effect   = "Allow"
        Action   = ["states:StartExecution", "states:ListExecutions"]
        Resource = aws_sfn_state_machine.pipeline.arn
      },
    ]
  })
}

output "state_machine_arn" { value = aws_sfn_state_machine.pipeline.arn }
output "upload_trigger_state" { value = aws_cloudwatch_event_rule.upload_trigger.state }
