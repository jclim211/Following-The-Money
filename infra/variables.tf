variable "region" {
  type    = string
  default = "us-east-1"
}

variable "account_id" {
  type    = string
  default = "761018854594"
}

variable "bucket" {
  type    = string
  default = "is459-g7-projectbucket"
}

variable "state_machine_name" {
  type    = string
  default = "is459-g7-pipeline"
}

# Names of resources first made by hand in the console. Check them with
#   aws stepfunctions describe-state-machine --state-machine-arn <arn> --query roleArn
#   aws events list-rules --name-prefix is459
variable "pipeline_role_name" {
  description = "IAM role the state machine runs as"
  type        = string
}

variable "trigger_rule_name" {
  description = "EventBridge rule that started the pipeline on every S3 upload. Terraform disables it."
  type        = string
}

variable "dashboard_role_name" {
  description = "Instance role of the EC2 dashboard server"
  type        = string
  default     = "is459-g7-dashboard-role"
}
