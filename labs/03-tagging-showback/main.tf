# Lab 3 - Tagging and showback
#
# 1. Turns the CostCenter / Owner / Environment tags into cost-allocation tags, so the bill can
#    be split by them in Cost Explorer.
# 2. An AWS Config rule (REQUIRED_TAGS) that flags resources missing any of them.
# 3. A monthly budget per cost center, filtered by tag, with a forecast alert.
# 4. A few S3 buckets (free when empty) - tagged for two cost centers and one deliberately
#    untagged - so you can watch the rule and the showback report work.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.region
}

# A second provider with no default tags, for the deliberately untagged example.
provider "aws" {
  alias  = "untagged"
  region = var.region
}

locals {
  name = "costlab-tagging"
  base_tags = {
    Project     = "aws-cost-optimization-labs"
    Lab         = "03-tagging-showback"
    Environment = "lab"
  }
}

data "aws_caller_identity" "current" {}

# --- 1. Cost-allocation tags ------------------------------------------------------------------
# A tag key can only be activated after it has appeared on at least one resource in billing data
# (up to 24 hours after first use), so this is off until you set activate_cost_allocation_tags.
resource "aws_ce_cost_allocation_tag" "required" {
  for_each = var.activate_cost_allocation_tags ? toset(var.required_tags) : toset([])
  tag_key  = each.value
  status   = "Active"
}

# --- 2. AWS Config: required tags --------------------------------------------------------------
resource "aws_s3_bucket" "config" {
  count         = var.create_config_recorder ? 1 : 0
  bucket        = "${local.name}-config-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  tags          = merge(local.base_tags, { CostCenter = "platform", Owner = var.owner })
}

resource "aws_s3_bucket_public_access_block" "config" {
  count                   = var.create_config_recorder ? 1 : 0
  bucket                  = aws_s3_bucket.config[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "config" {
  count  = var.create_config_recorder ? 1 : 0
  bucket = aws_s3_bucket.config[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "ConfigAclCheck"
        Effect    = "Allow"
        Principal = { Service = "config.amazonaws.com" }
        Action    = ["s3:GetBucketAcl", "s3:ListBucket"]
        Resource  = aws_s3_bucket.config[0].arn
        Condition = { StringEquals = { "AWS:SourceAccount" = data.aws_caller_identity.current.account_id } }
      },
      {
        Sid       = "ConfigWrite"
        Effect    = "Allow"
        Principal = { Service = "config.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.config[0].arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/Config/*"
        Condition = { StringEquals = { "s3:x-amz-acl" = "bucket-owner-full-control", "AWS:SourceAccount" = data.aws_caller_identity.current.account_id } }
      }
    ]
  })
}

resource "aws_iam_role" "config" {
  count = var.create_config_recorder ? 1 : 0
  name  = "${local.name}-config"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "config.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
  tags = merge(local.base_tags, { CostCenter = "platform", Owner = var.owner })
}

resource "aws_iam_role_policy_attachment" "config" {
  count      = var.create_config_recorder ? 1 : 0
  role       = aws_iam_role.config[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWS_ConfigRole"
}

resource "aws_config_configuration_recorder" "this" {
  count    = var.create_config_recorder ? 1 : 0
  name     = "${local.name}-recorder"
  role_arn = aws_iam_role.config[0].arn
  recording_group {
    all_supported = false
    resource_types = [
      "AWS::EC2::Instance", "AWS::EC2::Volume", "AWS::S3::Bucket", "AWS::RDS::DBInstance",
      "AWS::DynamoDB::Table", "AWS::ElasticLoadBalancingV2::LoadBalancer"
    ]
  }
}

resource "aws_config_delivery_channel" "this" {
  count          = var.create_config_recorder ? 1 : 0
  name           = "${local.name}-delivery"
  s3_bucket_name = aws_s3_bucket.config[0].id
  depends_on     = [aws_config_configuration_recorder.this, aws_s3_bucket_policy.config]
}

resource "aws_config_configuration_recorder_status" "this" {
  count      = var.create_config_recorder ? 1 : 0
  name       = aws_config_configuration_recorder.this[0].name
  is_enabled = true
  depends_on = [aws_config_delivery_channel.this]
}

resource "aws_config_config_rule" "required_tags" {
  name        = "${local.name}-required-tags"
  description = "Resources must carry ${join(", ", var.required_tags)}"
  source {
    owner             = "AWS"
    source_identifier = "REQUIRED_TAGS"
  }
  input_parameters = jsonencode({ for i, k in var.required_tags : "tag${i + 1}Key" => k })
  scope {
    compliance_resource_types = [
      "AWS::EC2::Instance", "AWS::EC2::Volume", "AWS::S3::Bucket", "AWS::RDS::DBInstance",
      "AWS::DynamoDB::Table", "AWS::ElasticLoadBalancingV2::LoadBalancer"
    ]
  }
  tags       = merge(local.base_tags, { CostCenter = "platform", Owner = var.owner })
  depends_on = [aws_config_configuration_recorder_status.this]
}

# --- 3. A budget per cost center ---------------------------------------------------------------
resource "aws_budgets_budget" "cost_center" {
  for_each     = var.cost_center_budgets
  name         = "${local.name}-${each.key}"
  budget_type  = "COST"
  limit_amount = tostring(each.value)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "TagKeyValue"
    values = [format("user:CostCenter$%s", each.key)]
  }

  dynamic "notification" {
    for_each = var.budget_alert_email == "" ? [] : [80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = notification.value == 100 ? "ACTUAL" : "FORECASTED"
      subscriber_email_addresses = [var.budget_alert_email]
    }
  }
}

# --- 4. Example resources ------------------------------------------------------------------------
resource "aws_s3_bucket" "tagged" {
  for_each      = toset(["web-team", "data"])
  bucket        = "${local.name}-${each.key}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  tags          = merge(local.base_tags, { CostCenter = each.key, Owner = var.owner, Name = "${local.name}-${each.key}" })
}

resource "aws_s3_bucket" "untagged" {
  provider      = aws.untagged
  bucket        = "${local.name}-untagged-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
  # No tags on purpose: AWS Config marks this NON_COMPLIANT and its cost lands in "(untagged)".
}
