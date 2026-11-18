# Changelog

## 1.0.0 - 2026-11-18

- **Lab 1, EC2 right-sizing:** four mis-sized instances with steady synthetic load and the CloudWatch agent for memory, plus a walkthrough comparing results with Compute Optimizer.
- **Lab 2, Spot and scheduled shutdown:**
  - A Spot-first Auto Scaling group with an On-Demand base, four instance types, price-capacity-optimized allocation and Capacity Rebalancing.
  - Scheduled scaling to zero overnight.
  - A tag-scoped stop/start Lambda run by EventBridge Scheduler.
- **Lab 3, tagging and showback:** cost-allocation tags, an AWS Config REQUIRED_TAGS rule, a monthly budget per cost center filtered by tag, and tagged and untagged example buckets.
- **Lab 4, EKS with Karpenter:** EKS 1.36 and Karpenter 1.14 LTS (terraform-aws-modules v21), with a Spot-first NodePool, WhenEmptyOrUnderutilized consolidation, CPU and memory limits, and a scale-out / consolidate / scale-to-zero walkthrough.
- **costlab:** read-only analysis tool with these commands:
  - `rightsize`: idle, downsize, upsize, burst-bound and keep, with Graviton options. It projects CPU by vCPU and memory by GiB, and respects T-instance credit baselines.
  - `schedule` and `spot`.
  - `showback`, which reports untagged share and trend.
  - `eks`.
  - `report`, which writes one HTML report.
  - A `--demo` account, plus `--live-pricing` through the AWS Pricing API.
- Tests: pytest suite including the scheduler Lambda and the Karpenter manifests.
- CI: tests run on Python 3.9 and 3.12, and `terraform validate` runs on every lab.
