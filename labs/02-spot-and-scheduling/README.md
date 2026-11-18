# Lab 2 - Spot and scheduled shutdown

**Goal:** stop paying for capacity nobody is using (nights, weekends) and pay Spot prices for capacity that can tolerate an interruption.

**Cost while running:** about $0.04 an hour in daytime (one On-Demand and two Spot t3/t3a micro/small instances plus a t3.micro), close to zero at night. Lambda and EventBridge Scheduler stay inside the free tier.

## What it builds

| Part | How it saves | Typical saving |
|---|---|---|
| Auto Scaling group: 1 On-Demand base, the rest Spot over four instance types (`price-capacity-optimized`, Capacity Rebalancing on) | Spot capacity is billed at the Spot price | Often 60-70% on the Spot share |
| Scheduled scaling: desired capacity 0 at 19:00, back to 3 at 07:00, Monday to Friday | The group only runs 60 of 168 hours | About 64% |
| Lambda + EventBridge Scheduler: stops/starts instances tagged `Schedule=office-hours` | Same schedule for instances outside an Auto Scaling group | About 64% |

The Lambda's IAM policy only allows stop/start on instances that carry the tag, so it can't touch anything else.

## Steps

```bash
terraform init
terraform apply
terraform output -raw try_it
```

1. **See the Spot mix.** Run the first command from `try_it`. One instance shows `on-demand`, the others `spot`.
2. **Compare prices:**
   ```bash
   cd ../..
   python -m costlab spot --region us-east-1 --types t3.micro t3a.micro t3.small t3a.small m6i.large
   ```
3. **Rehearse an interruption.** Spot gives a two-minute warning. Use AWS Fault Injection Service with the `aws:ec2:send-spot-instance-interruptions` action on one of the group's Spot instances. The group launches a replacement, from a different pool if that one is short, without you doing anything.
4. **Run the schedule now.** Invoke the Lambda with the second `try_it` command and watch the dev box stop. The 07:00 schedule starts it again (or invoke it with `{"action":"start"}`).
5. **Price the schedule across the account:**
   ```bash
   python -m costlab schedule --region us-east-1 --html schedule.html
   ```

## Choosing what goes on Spot

- **Good fits:** stateless web and API tiers behind a load balancer, CI runners, batch and queue workers, dev/test, containers on EKS or ECS.
- **Poor fits:** single-instance databases, anything that can't checkpoint or drain within two minutes.
- **Diversify.** Every extra instance type and Availability Zone is another capacity pool. `price-capacity-optimized` picks pools that are both cheap and deep, which keeps interruptions rare.
- **Keep a base.** `on_demand_base_capacity` keeps a floor that never gets interrupted.

Schedules pair well with Savings Plans: commit only to the always-on baseline, and let scheduling and Spot handle the rest.

## Clean up

```bash
terraform destroy
```
