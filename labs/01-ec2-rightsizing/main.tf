# Lab 1 - EC2 right-sizing
#
# Launches a few deliberately mis-sized instances with a known, steady CPU load and the
# CloudWatch agent (for memory), so `costlab rightsize` has real metrics to work on.
# Access is through SSM Session Manager - no inbound ports, no SSH keys.

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = local.tags }
}

locals {
  name = "costlab-rightsizing"
  tags = {
    Project     = "aws-cost-optimization-labs"
    Lab         = "01-ec2-rightsizing"
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

# --- Instance role: Session Manager + CloudWatch agent ---
resource "aws_iam_role" "instance" {
  name = "${local.name}-instance"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "cloudwatch_agent" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

resource "aws_iam_instance_profile" "instance" {
  name = "${local.name}-instance"
  role = aws_iam_role.instance.name
}

resource "aws_security_group" "instance" {
  name        = "${local.name}-sg"
  description = "No inbound access; outbound for package installs and SSM"
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "lab" {
  for_each = var.instances

  ami                    = nonsensitive(data.aws_ssm_parameter.al2023.value)
  instance_type          = each.value.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.instance.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name
  user_data              = templatefile("${path.module}/user-data.sh.tftpl", { cpu_load = each.value.cpu_load })

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name    = each.key
    CpuLoad = tostring(each.value.cpu_load)
  }
}
