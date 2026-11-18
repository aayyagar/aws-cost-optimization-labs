output "configure_kubectl" {
  value = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "karpenter_manifest" {
  description = "EC2NodeClass and NodePool for this cluster. Apply with: terraform output -raw karpenter_manifest | kubectl apply -f -"
  value = templatefile("${path.module}/manifests/karpenter.yaml.tftpl", {
    cluster_name   = module.eks.cluster_name
    node_role      = module.karpenter.node_iam_role_name
    capacity_types = jsonencode(var.spot_and_on_demand)
    cost_center    = var.cost_center
  })
}
