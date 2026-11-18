"""A fictional AWS account for --demo runs: no credentials, same code paths."""
from __future__ import annotations

from .rightsizing import Usage
from .showback import CostLine

USAGE = [
    Usage("i-0a1f3c9e7d2b40001", "web-01", "m6i.2xlarge", 18.0, 41.0, 31.0, "web-team"),
    Usage("i-0a1f3c9e7d2b40002", "web-02", "m6i.2xlarge", 21.0, 44.0, 33.0, "web-team"),
    Usage("i-0a1f3c9e7d2b40003", "reporting-batch", "c6i.4xlarge", 9.0, 62.0, 22.0, "finance"),
    Usage("i-0a1f3c9e7d2b40004", "jenkins-agent-old", "m5.xlarge", 0.8, 2.6, 12.0, "platform"),
    Usage("i-0a1f3c9e7d2b40005", "api-gateway-svc", "c6i.xlarge", 91.0, 99.0, 58.0, "web-team"),
    Usage("i-0a1f3c9e7d2b40006", "analytics-db", "r6i.2xlarge", 46.0, 77.0, 81.0, "data"),
    Usage("i-0a1f3c9e7d2b40007", "dev-sandbox-amy", "t3.xlarge", 6.0, 38.0, None, "platform"),
    Usage("i-0a1f3c9e7d2b40008", "bastion", "t3.medium", 1.1, 4.1, 9.0, "platform"),
    Usage("i-0a1f3c9e7d2b40009", "etl-worker", "m5.2xlarge", 52.0, 88.0, 47.0, "data"),
    Usage("i-0a1f3c9e7d2b4000a", "ci-runner", "t3.medium", 34.0, 71.0, 44.0, "platform"),
]

# (instance id, name, type, schedule tag)
SCHEDULED = [
    ("i-0b2e4d6f8a1c30001", "dev-api-01", "m6i.xlarge", "office-hours"),
    ("i-0b2e4d6f8a1c30002", "dev-api-02", "m6i.xlarge", "office-hours"),
    ("i-0b2e4d6f8a1c30003", "qa-selenium", "c6i.2xlarge", "office-hours"),
    ("i-0b2e4d6f8a1c30004", "uat-app", "m5.large", "extended-hours"),
    ("i-0b2e4d6f8a1c30005", "training-lab", "t3.large", "office-hours"),
]

# Illustrative Spot prices (USD/hour). Live runs read describe-spot-price-history instead.
SPOT = {"m6i.large": 0.0368, "m6i.xlarge": 0.0741, "c6i.xlarge": 0.0702, "m7g.large": 0.0331, "t3.large": 0.0301, "r6i.large": 0.0412}


def cost_lines() -> list[CostLine]:
    base = {
        "web-team": {"Amazon Elastic Compute Cloud - Compute": 6120, "Amazon Relational Database Service": 2380, "Amazon CloudFront": 610, "Elastic Load Balancing": 420},
        "data": {"Amazon Elastic Compute Cloud - Compute": 3890, "Amazon Simple Storage Service": 1740, "Amazon Redshift": 2950, "AWS Glue": 680},
        "finance": {"Amazon Elastic Compute Cloud - Compute": 1460, "Amazon Simple Storage Service": 220, "Amazon QuickSight": 310},
        "platform": {"Amazon Elastic Compute Cloud - Compute": 2210, "Amazon Elastic Kubernetes Service": 730, "Amazon CloudWatch": 540, "AWS Config": 190},
        "": {"Amazon Elastic Compute Cloud - Compute": 2640, "Amazon Simple Storage Service": 960, "Amazon Elastic Block Store": 880, "EC2 - Other": 1120, "AWS Lambda": 140},
    }
    growth = {"2026-08": 0.96, "2026-09": 1.0, "2026-10": 1.07}
    untagged_trend = {"2026-08": 1.18, "2026-09": 1.0, "2026-10": 0.81}   # tagging policy kicking in
    out = []
    for month, g in growth.items():
        for owner, services in base.items():
            f = g * (untagged_trend[month] if owner == "" else 1)
            for svc, amt in services.items():
                out.append(CostLine(month, owner, svc, round(amt * f, 2)))
    return out
