# Lab 4 - EKS autoscaling with Karpenter

**Goal:** stop paying for idle Kubernetes nodes. Karpenter launches the node that fits the pending pods (Spot first), and keeps consolidating: empty nodes are removed and under-used ones are replaced with fewer or cheaper ones.

**Cost while running:** about $0.35 an hour: EKS control plane $0.10, two m5.large system nodes about $0.19, one NAT gateway about $0.045, plus whatever Karpenter launches while you scale the demo workload. Destroy the same day.

## What it builds

- A VPC across three AZs: private subnets for nodes, one NAT gateway.
- EKS 1.36 with a two-node Bottlerocket managed node group labelled `karpenter.sh/controller=true`. It runs system pods and the Karpenter controller, never your workloads.
- Karpenter 1.14 LTS (Helm, EKS Pod Identity, an SQS interruption queue for Spot warnings and health events), via the `terraform-aws-modules/eks` v21 Karpenter submodule.
- An `EC2NodeClass` and `NodePool` (rendered by Terraform), with:
  - Spot and On-Demand allowed. Karpenter picks Spot when it can.
  - c, m or r families from generation 6 up, on x86 or Arm.
  - `WhenEmptyOrUnderutilized` consolidation after 1 minute.
  - A 64 vCPU limit, so a runaway deployment can't buy unlimited capacity.
  - Nodes replaced every 30 days.

## Steps

```bash
terraform init
terraform apply                                   # about 15 minutes
$(terraform output -raw configure_kubectl)
terraform output -raw karpenter_manifest | kubectl apply -f -
kubectl apply -f manifests/inflate.yaml
```

1. **Baseline.** `python -m costlab eks` (run from the repo root) prices the two system nodes.
2. **Scale out.**
   ```bash
   kubectl scale deployment inflate --replicas 10
   kubectl get nodeclaims -w            # Karpenter launches a node for the 10 pending pods in about a minute
   kubectl get nodes -L karpenter.sh/capacity-type,node.kubernetes.io/instance-type
   ```
   You get one or two right-sized Spot nodes, not a fixed-size node per replica. Run `python -m costlab eks` again.
3. **Scale in and watch consolidation.**
   ```bash
   kubectl scale deployment inflate --replicas 3
   kubectl logs -n kube-system -l app.kubernetes.io/name=karpenter -f | grep -i -E "disrupt|consolidat"
   ```
   About a minute later Karpenter replaces the node with a smaller one, or removes it if the pods fit elsewhere.
4. **Scale to zero.** `kubectl scale deployment inflate --replicas 0`. The Karpenter node disappears and you're back to the two system nodes.
5. **Try On-Demand only.** `terraform apply -var 'spot_and_on_demand=["on-demand"]'`, re-apply the manifest, repeat step 2 and compare the `costlab eks` numbers.

Keep the Kubernetes version in standard support: a cluster in extended support costs several times more per hour, which would undo the savings this lab is about. When you change `kubernetes_version`, check the [Karpenter compatibility matrix](https://karpenter.sh/docs/upgrading/compatibility/) and raise `karpenter_version` with it.

## Why it saves money

| Cluster Autoscaler + fixed node groups | Karpenter |
|---|---|
| Scales node groups of one instance shape | Chooses from hundreds of instance types per pending batch |
| Removes a node only when it's nearly empty | Consolidates: replaces under-used nodes with cheaper ones |
| Spot needs separate node groups per type | Spot and On-Demand in one NodePool, Spot preferred, interruption handling built in |

Savings depend on how well pod requests match real use. Karpenter packs by **requests**, so over-sized requests still waste money. Use the Vertical Pod Autoscaler recommender or the request-vs-usage view in your monitoring to tune them.

Protect pods that must not move with `karpenter.sh/do-not-disrupt: "true"` and a PodDisruptionBudget.

## Clean up

Remove Karpenter's nodes before destroying the cluster, so nothing outlives Terraform:

```bash
kubectl delete deployment inflate
kubectl delete nodepool default && kubectl delete ec2nodeclass default
terraform destroy
```
