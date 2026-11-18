# Lab 2 - Spot and scheduled shutdown
#
# 1. An Auto Scaling group that keeps one On-Demand instance and runs the rest on Spot across
#    several instance types (price-capacity-optimized), with Capacity Rebalancing.
# 2. Scheduled scaling that takes the group to zero at night and back in the morning.
# 3. A small Lambda, run by EventBridge Scheduler, that stops and starts any instance tagged
#    Schedule=office-hours - the pattern for instances that are not in an Auto Scaling group.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 5.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.4" }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = local.tags }
}

locals {
  name = "costlab-spot"
  tags = {
    Project     = "aws-cost-optimization-labs"
    Lab         = "02-spot-and-scheduling"
    CostCenter  = var.cost_center
    Owner       = var.owner
    Environment = "lab"
  }
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_security_group" "lab" {
  name        = "${local.name}-sg"
  description = "No inbound access"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# --- 1. Spot-first Auto Scaling group --------------------------------------------------------
resource "aws_launch_template" "web" {
  name_prefix            = "${local.name}-"
  image_id               = nonsensitive(data.aws_ssm_parameter.al2023.value)
  vpc_security_group_ids = [aws_security_group.lab.id]

  metadata_options {
    http_tokens = "required"
  }

  tag_specifications {
    resource_type = "instance"
    tags          = merge(local.tags, { Name = "${local.name}-web" })
  }
  tag_specifications {
    resource_type = "volume"
    tags          = local.tags
  }
}

resource "aws_autoscaling_group" "web" {
  name                = "${local.name}-web"
  vpc_zone_identifier = data.aws_subnets.default.ids
  min_size            = 0
  max_size            = var.max_size
  desired_capacity    = var.daytime_capacity
  capacity_rebalance  = true # replace Spot instances proactively when AWS signals a higher interruption risk

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = var.on_demand_base
      on_demand_percentage_above_base_capacity = 0
      spot_allocation_strategy                 = "price-capacity-optimized"
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.web.id
        version            = "$Latest"
      }
      dynamic "override" {
        for_each = var.instance_types
        content {
          instance_type = override.value
        }
      }
    }
  }

  dynamic "tag" {
    for_each = merge(local.tags, { Name = "${local.name}-web" })
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = true
    }
  }

  lifecycle {
    ignore_changes = [desired_capacity] # the schedules below own it
  }
}

# --- 2. Scheduled scaling: zero overnight and at weekends ------------------------------------
resource "aws_autoscaling_schedule" "evening" {
  scheduled_action_name  = "scale-to-zero"
  autoscaling_group_name = aws_autoscaling_group.web.name
  recurrence             = "0 ${var.stop_hour} * * MON-FRI"
  time_zone              = var.time_zone
  min_size               = 0
  max_size               = var.max_size
  desired_capacity       = 0
}

resource "aws_autoscaling_schedule" "morning" {
  scheduled_action_name  = "scale-to-daytime"
  autoscaling_group_name = aws_autoscaling_group.web.name
  recurrence             = "0 ${var.start_hour} * * MON-FRI"
  time_zone              = var.time_zone
  min_size               = 0
  max_size               = var.max_size
  desired_capacity       = var.daytime_capacity
}

# --- 3. Tag-driven stop/start for standalone instances ---------------------------------------
resource "aws_instance" "dev" {
  ami                    = nonsensitive(data.aws_ssm_parameter.al2023.value)
  instance_type          = "t3.micro"
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.lab.id]

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name     = "${local.name}-dev-box"
    Schedule = var.schedule_tag_value
  }
}

data "archive_file" "scheduler" {
  type        = "zip"
  source_file = "${path.module}/lambda/scheduler.py"
  output_path = "${path.module}/.build/scheduler.zip"
}

resource "aws_iam_role" "lambda" {
  name = "${local.name}-scheduler-fn"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_ec2" {
  name = "stop-start-scheduled-instances"
  role = aws_iam_role.lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "Find", Effect = "Allow", Action = "ec2:DescribeInstances", Resource = "*" },
      {
        Sid      = "OnlyTaggedInstances"
        Effect   = "Allow"
        Action   = ["ec2:StopInstances", "ec2:StartInstances"]
        Resource = "arn:aws:ec2:${var.region}:*:instance/*"
        Condition = {
          StringEquals = { "aws:ResourceTag/${var.schedule_tag_key}" = var.schedule_tag_value }
        }
      }
    ]
  })
}

resource "aws_lambda_function" "scheduler" {
  function_name    = "${local.name}-scheduler"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "scheduler.handler"
  filename         = data.archive_file.scheduler.output_path
  source_code_hash = data.archive_file.scheduler.output_base64sha256
  timeout          = 60
  environment {
    variables = {
      TAG_KEY   = var.schedule_tag_key
      TAG_VALUE = var.schedule_tag_value
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name = "${local.name}-eventbridge-scheduler"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "scheduler.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  name = "invoke-scheduler-fn"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_function.scheduler.arn }]
  })
}

resource "aws_scheduler_schedule" "stop" {
  name                         = "${local.name}-stop"
  schedule_expression          = "cron(0 ${var.stop_hour} ? * MON-FRI *)"
  schedule_expression_timezone = var.time_zone
  flexible_time_window {
    mode = "OFF"
  }
  target {
    arn      = aws_lambda_function.scheduler.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ action = "stop" })
  }
}

resource "aws_scheduler_schedule" "start" {
  name                         = "${local.name}-start"
  schedule_expression          = "cron(0 ${var.start_hour} ? * MON-FRI *)"
  schedule_expression_timezone = var.time_zone
  flexible_time_window {
    mode = "OFF"
  }
  target {
    arn      = aws_lambda_function.scheduler.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ action = "start" })
  }
}
