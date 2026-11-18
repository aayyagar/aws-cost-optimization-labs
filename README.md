# AWS Cost-Optimization Labs

Four hands-on labs for the AWS savings that matter most, each with Terraform to build it and a read-only analysis tool (`costlab`) to measure it:

1. **EC2 right-sizing:** find oversized and idle instances from real CloudWatch metrics.
2. **Spot and scheduled shutdown:** stop paying for nights and weekends, and pay Spot prices where interruptions are fine.
3. **Tagging and showback:** make every dollar traceable to a team and catch untagged spend.
4. **EKS autoscaling with Karpenter:** right-sized, consolidated, Spot-first Kubernetes nodes.

**[View the sample report →](https://aayyagar.github.io/aws-cost-optimization-labs/sample-report/)** · Python 3.9+ · Terraform 1.5+ · MIT license

```text
$ python -m costlab report --demo --html report.html

== rightsize
  [Idle       ] jenkins-agent-old    m5.xlarge    -> -            save $140.16/mo
  [Idle       ] bastion              t3.medium    -> -            save $30.37/mo
  [Downsize   ] reporting-batch      c6i.4xlarge  -> c6i.2xlarge  save $248.20/mo
  [Downsize   ] web-01               m6i.2xlarge  -> m6i.xlarge   save $140.16/mo
  ...
  Potential saving: $759.78 per month

== showback
  web-team       $ 10,197.10  (2026-10)
  ...
  (untagged)     $  4,974.86  (2026-10)
  Untagged: 18.9% of spend
```

---

## The labs

| Lab | Builds | You learn to | Cost while running |
|---|---|---|---|
| [01 - EC2 right-sizing](labs/01-ec2-rightsizing/) | Four mis-sized instances with steady synthetic load and the CloudWatch agent | Read p95 CPU and memory, tell idle from oversized from burst-bound, compare with Compute Optimizer, resize safely | ~$0.16/h |
| [02 - Spot and scheduling](labs/02-spot-and-scheduling/) | Spot-first Auto Scaling group, scheduled scaling, tag-driven stop/start Lambda | Mix On-Demand and Spot, survive interruptions, cut nights and weekends | ~$0.04/h |
| [03 - Tagging and showback](labs/03-tagging-showback/) | Cost-allocation tags, AWS Config required-tags rule, a budget per cost center | Enforce tags, split the bill by team, find untagged spend | ~$0 |
| [04 - EKS with Karpenter](labs/04-eks-karpenter/) | EKS 1.36, a small system node group, Karpenter 1.14 with a Spot-first NodePool | Watch Karpenter scale out, consolidate and scale to zero | ~$0.35/h |

Each lab is a separate Terraform root, so build only the one you're working on, and **run `terraform destroy` when you finish**. Everything is tagged `Project=aws-cost-optimization-labs` and `CostCenter`, which Lab 3 uses for showback.

## costlab

Read-only analysis for each lab. It only calls describe, list and get APIs (EC2, CloudWatch, Cost Explorer, Pricing, Resource Groups Tagging), plus `kubectl get` for Lab 4.

| Command | Lab | What it does |
|---|---|---|
| `python -m costlab rightsize` | 1 | Idle / Downsize / Upsize / Burst-bound / Keep for each running instance, monthly saving, Graviton option |
| `python -m costlab schedule` | 2 | Saving for each instance tagged `Schedule` (`office-hours`, `extended-hours` or `name:07-19:Mon-Fri`) |
| `python -m costlab spot` | 2 | Current Spot price against On-Demand for the types you pass |
| `python -m costlab showback` | 3 | Monthly cost per `CostCenter`, top services per team, share and trend of untagged spend |
| `python -m costlab eks` | 4 | Prices the cluster's nodes by type and capacity type |
| `python -m costlab report` | all | Runs everything and writes one HTML report |

Add `--demo` to any command to use a built-in fictional account (no AWS credentials needed), `--html` / `--json` to save results, and `--live-pricing` to read prices from the AWS Pricing API instead of the bundled us-east-1 list prices.

```bash
pip install boto3                 # only needed for live runs
aws sso login                     # or any credentials with read access
python -m costlab report --region us-east-1 --html report.html
```

### How right-sizing decides

- It uses **p95** CPU and memory over the window (14 days by default). Memory comes from the CloudWatch agent (`CWAgent / mem_used_percent`). Without it, the tool never recommends more than halving memory.
- It **projects** CPU by vCPU count and memory by GiB on each smaller size. It downsizes while the projection stays at or below **60% CPU** and **75% memory**, and below the target's CPU-credit baseline on T instances.
- **Idle** means CPU never went above 5%. **Upsize** means p95 is above 85% CPU or 90% memory. **Burst-bound** means a T instance sits above its credit baseline all day and belongs on a fixed-performance type.
- It shows the **Graviton** equivalent (t4g, m7g, c7g, r7g) as an option, because it needs Arm builds of the software.

### Permissions

Read-only. Cost Explorer calls are $0.01 each and the report makes a handful.

`ec2:DescribeInstances`, `ec2:DescribeSpotPriceHistory`, `cloudwatch:GetMetricStatistics`, `ce:GetCostAndUsage`, `pricing:GetProducts`, `tag:GetResources`, and `eks:DescribeCluster` (for `kubectl` access).

## Order of savings

Do it in this order:

1. **Turn off what nobody uses.** Idle instances, unattached EBS volumes, old snapshots.
2. **Right-size what's left** (Lab 1).
3. **Schedule non-production** (Lab 2).
4. **Move interruption-tolerant capacity to Spot** (Labs 2 and 4).
5. **Commit to the steady baseline that remains**, with Savings Plans or Reserved Instances.

Committing first locks in the waste. Tagging and showback (Lab 3) run alongside all of it, so each team can see its own number move.

## Repository layout

```text
costlab/                     analysis tool (Python, standard library + boto3 for live runs)
labs/01-ec2-rightsizing/     Terraform + walkthrough
labs/02-spot-and-scheduling/ Terraform, scheduler Lambda + walkthrough
labs/03-tagging-showback/    Terraform + walkthrough
labs/04-eks-karpenter/       Terraform, Karpenter manifests + walkthrough
sample-report/               the published demo report
tests/                       pytest
```

Run the tests with `python -m pytest tests`. CI also runs `terraform validate` on every lab.

## Author

**Akhilesh Ayyagari**, Cloud Infrastructure & Identity Architect · [Portfolio](https://aayyagar.github.io) · [LinkedIn](https://www.linkedin.com/in/akhilesh-ayyagari)

## License

MIT
