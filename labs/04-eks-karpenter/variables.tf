variable "region" {
  type    = string
  default = "us-east-1"
}

variable "cluster_name" {
  type    = string
  default = "costlab-karpenter"
}

variable "kubernetes_version" {
  description = "EKS version. 1.36 is in standard support until Aug 2027; versions in extended support cost much more per cluster hour."
  type        = string
  default     = "1.36"
}

variable "karpenter_version" {
  description = "Karpenter Helm chart version. 1.14 is an LTS release and supports Kubernetes 1.36 (see karpenter.sh compatibility matrix)."
  type        = string
  default     = "1.14.3"
}

variable "system_instance_type" {
  type    = string
  default = "m5.large"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "cost_center" {
  type    = string
  default = "platform"
}

variable "owner" {
  type    = string
  default = "cost-lab"
}

variable "spot_and_on_demand" {
  description = "Capacity types Karpenter may launch. Karpenter prefers Spot when both are allowed."
  type        = list(string)
  default     = ["spot", "on-demand"]
}
