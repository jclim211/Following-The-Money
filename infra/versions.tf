terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
  # State lives in the project bucket. use_lockfile needs Terraform 1.10 or newer.
  backend "s3" {
    bucket       = "is459-g7-projectbucket"
    key          = "tfstate/pipeline.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = { project = "is459-g7", managed_by = "terraform" } }
}
