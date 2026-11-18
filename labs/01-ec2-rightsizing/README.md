# Lab 1 - EC2 right-sizing

**Goal:** find instances that are bigger than their load needs (or doing nothing at all), pick the right size from real metrics, and know how much it saves.

**Cost while running:** about $0.16 an hour for the four default instances (t3.large, t3.medium, t3.small, t3.micro), plus CPU-credit charges on the credit burner. Destroy when you finish.

## What it builds

| Instance | Type | Load | What you should find |
|---|---|---|---|
| `rs-oversized-web` | t3.large | steady 8% CPU | Downsize, most likely to t3.micro: same 2 vCPUs, and 8% fits under the micro's 10% credit baseline |
| `rs-idle-box` | t3.medium | none | Idle: stop or terminate |
| `rs-right-sized` | t3.micro | steady 6% CPU | Keep (t3.nano's 5% baseline is too low); a Graviton t4g.micro is cheaper |
| `rs-credit-burner` | t3.small | steady 35% CPU | Burst-bound: above its 20% baseline, so it spends credits all day. Move to a fixed-performance type |

Each instance runs the CloudWatch agent, so memory (`CWAgent / mem_used_percent`) is available as well as CPU. Without memory data the tool only ever recommends one step down, because CPU alone can hide a memory-bound workload. There are no inbound ports: connect with Session Manager.

## Steps

```bash
terraform init
terraform apply
```

1. **Wait for data.** Right-sizing needs history: give it at least 24 hours (14 days in real life, to include a month-end or a batch run).
2. **Look at the metrics yourself.** In CloudWatch, compare `CPUUtilization` p95 and `mem_used_percent` for the three instances.
3. **Run the analysis:**
   ```bash
   cd ../..
   python -m costlab rightsize --region us-east-1 --days 1 --html rightsizing.html
   python -m costlab rightsize --region us-east-1 --days 1 --live-pricing   # prices from the AWS Pricing API
   ```
4. **Compare with AWS Compute Optimizer** (free; opt in once per account; it needs at least 30 hours of metrics before it recommends anything):
   ```bash
   aws compute-optimizer update-enrollment-status --status Active
   aws compute-optimizer get-ec2-instance-recommendations \
     --query 'instanceRecommendations[].{id:instanceArn,now:currentInstanceType,finding:finding,best:recommendationOptions[0].instanceType}'
   ```
5. **Apply a recommendation.** Change `instance_type` for `rs-oversized-web` in `variables.tf` (or a `.tfvars` file) and `terraform apply`: Terraform stops the instance, changes the type and starts it.

## How the recommendation works

- **p95, not average.** The 95th percentile ignores the odd spike but still captures the busy part of the day.
- **Projection by capacity.** CPU is projected by vCPU count and memory by GiB. On fixed-performance families (m, c, r) each step down halves both, so 20% CPU on an xlarge becomes about 40% on a large. T instances keep 2 vCPUs from nano to large, so stepping down a T size changes memory and the credit baseline, not the CPU percentage.
- **Targets.** Downsize while projected p95 stays at or below 60% CPU and 75% memory, and on T instances under the target size's credit baseline. Upsize above 85% CPU or 90% memory.
- **Burst-bound.** A T instance whose p95 sits above its own baseline is spending CPU credits all day; it is flagged with the cheapest fixed-performance type of the same shape.
- **Idle.** Maximum CPU below 5% over the whole window means stop it, or snapshot and terminate it.
- **Graviton.** The same size on Arm (t4g, m7g, c7g, r7g) usually costs 10-20% less. It needs Arm builds of your software, so it's shown as an option, not the recommendation.

CPU-credit baselines per vCPU: t3.nano 5%, micro 10%, small and medium 20%, large 30%, xlarge and 2xlarge 40%.

## Clean up

```bash
terraform destroy
```
