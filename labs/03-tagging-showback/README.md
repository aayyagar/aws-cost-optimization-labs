# Lab 3 - Tagging and showback

**Goal:** make every dollar traceable to a team. Enforce a tagging standard, turn the tags into cost-allocation tags, show each team its own spend (showback), and alert before a team goes over budget.

**Cost:** close to zero. Empty S3 buckets cost nothing, budgets cost little or nothing (see AWS Budgets pricing), and AWS Config charges per configuration item recorded, which is a few cents for this lab.

## What it builds

| Part | Why |
|---|---|
| Cost-allocation tags `CostCenter`, `Owner`, `Environment` | Cost Explorer and the Cost and Usage Report can only group by tags that are activated |
| AWS Config `REQUIRED_TAGS` rule | Shows every EC2 instance, EBS volume, S3 bucket, RDS instance, DynamoDB table and load balancer missing a required tag |
| A monthly budget per cost center, filtered by `CostCenter` | Each team gets its own forecast alert at 80% and actual alert at 100% |
| Two tagged buckets and one untagged bucket | So you can see the rule and the report pick up the difference |

## Steps

```bash
terraform init
terraform apply -var budget_alert_email=you@example.com
# If the account already has an AWS Config recorder:  -var create_config_recorder=false
```

1. **See the gap.** After a few minutes, run `terraform output -raw check_compliance`. The untagged bucket is listed as non-compliant.
2. **Activate the tags for billing.** A tag key can only be activated once it shows up in billing data, up to 24 hours after first use. Then:
   ```bash
   terraform apply -var activate_cost_allocation_tags=true
   ```
   Cost Explorer starts grouping by the tag from that point on. Activation is not retroactive.
3. **Run the showback report:**
   ```bash
   cd ../..
   python -m costlab showback --tag-key CostCenter --months 3 --html showback.html
   ```
   Each team's monthly cost appears, with its top services and the share of spend nobody owns.
4. **Fix the untagged spend.** Use the report's top untagged services and the Config rule to find owners. Tag at creation time: `default_tags` in Terraform, tag-on-create in CloudFormation, required tags in Service Catalog. For a multi-account organization, add an Organizations tag policy so `CostCenter` values are spelled consistently.

## Showback, then chargeback

Showback means each team sees what it spends. Chargeback means the bill actually moves to the team's budget. Start with showback: once untagged spend is under about 5% and the numbers are trusted, chargeback becomes a finance decision, not a data problem.

Shared costs (support plan, networking, shared clusters) need an agreed split rule, such as proportional to each team's direct spend. Write the rule down before anyone asks.

## Clean up

```bash
terraform destroy
```

Cost-allocation tags stay active after destroy, which does no harm.
