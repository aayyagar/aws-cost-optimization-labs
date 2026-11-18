# Lab 4 - EKS autoscaling with Karpenter
#
# A small EKS cluster: a two-node managed node group that only runs system pods and the
# Karpenter controller, and Karpenter for everything else. Karpenter launches the cheapest
# node that fits the pending pods (Spot first), and consolidates or removes under-used nodes.
#
# Uses the community terraform-aws-modules VPC (v6) and EKS (v21) modules, following the
# module's own Karpenter example, with Kubernetes 1.36 and Karpenter 1.14 (LTS).

terraform {
  required_version = ">= 1.5.7"
  required_providers {
    aws  = { source = "hashicorp/aws", version = "~> 6.59" }
    helm = { source = "hashicorp/helm", version = "~> 3.0" }
  }
}

provider "aws" {
  region = var.region
  default_tags { tags = local.tags }
}

provider "helm" {
  kubernetes = {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name, "--region", var.region]
    }
  }
}

locals {
  name = var.cluster_name
  azs  = slice(data.aws_availability_zones.available.names, 0, 3)
  tags = {
    Project     = "aws-cost-optimization-labs"
    Lab         = "04-eks-karpenter"
    CostCenter  = var.cost_center
    Owner       = var.owner
    Environment = "lab"
  }
}

data "aws_availability_zones" "available" {
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

# The Karpenter chart is in ECR Public, whose auth endpoint is in us-east-1 only.
data "aws_ecrpublic_authorization_token" "token" {
  region = "us-east-1"
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"

  name            = local.name
  cidr            = var.vpc_cidr
  azs             = local.azs
  private_subnets = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 48)]
  intra_subnets   = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 52)]

  enable_nat_gateway = true
  single_nat_gateway = true # one NAT gateway is enough for a lab and halves its cost

  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1, "karpenter.sh/discovery" = local.name }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.30"

  name                                     = local.name
  kubernetes_version                       = var.kubernetes_version
  endpoint_public_access                   = true
  enable_cluster_creator_admin_permissions = true

  addons = {
    coredns = {}
    eks-pod-identity-agent = {
      before_compute = true
    }
    kube-proxy = {}
    vpc-cni = {
      before_compute = true
    }
  }

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.intra_subnets

  # A small fixed node group for system pods and the Karpenter controller itself.
  eks_managed_node_groups = {
    system = {
      ami_type       = "BOTTLEROCKET_x86_64"
      instance_types = [var.system_instance_type]
      min_size       = 2
      max_size       = 3
      desired_size   = 2
      labels         = { "karpenter.sh/controller" = "true" }
    }
  }

  # Only this security group carries the discovery tag, so Karpenter nodes join it.
  node_security_group_tags = { "karpenter.sh/discovery" = local.name }
}

module "karpenter" {
  source  = "terraform-aws-modules/eks/aws//modules/karpenter"
  version = "~> 21.30"

  cluster_name                    = module.eks.cluster_name
  create_pod_identity_association = true

  node_iam_role_use_name_prefix = false
  node_iam_role_name            = "${local.name}-karpenter-node"
  node_iam_role_additional_policies = {
    AmazonSSMManagedInstanceCore = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  }
}

resource "helm_release" "karpenter" {
  namespace           = "kube-system"
  name                = "karpenter"
  repository          = "oci://public.ecr.aws/karpenter"
  repository_username = data.aws_ecrpublic_authorization_token.token.user_name
  repository_password = data.aws_ecrpublic_authorization_token.token.password
  chart               = "karpenter"
  version             = var.karpenter_version
  wait                = false

  values = [<<-EOT
    nodeSelector:
      karpenter.sh/controller: "true"
    dnsPolicy: Default
    settings:
      clusterName: ${module.eks.cluster_name}
      clusterEndpoint: ${module.eks.cluster_endpoint}
      interruptionQueue: ${module.karpenter.queue_name}
  EOT
  ]
}
