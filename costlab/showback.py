"""Lab 3 - tagging and showback.

Groups the bill by a cost-allocation tag (CostCenter by default) so each team sees what it
spends, and measures how much spend carries no tag at all - the number that tells you whether
your tagging policy works.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict

UNTAGGED = "(untagged)"


@dataclass
class CostLine:
    month: str        # YYYY-MM
    tag_value: str    # "" when the resource has no tag
    service: str
    amount: float


@dataclass
class Showback:
    tag_key: str
    months: list[str]
    by_owner: dict[str, dict[str, float]]          # owner -> month -> amount
    by_owner_service: dict[str, dict[str, float]]  # owner -> service -> amount (whole period)
    totals: dict[str, float]                       # month -> amount
    untagged_pct: float
    top_untagged_services: list[tuple[str, float]]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["top_untagged_services"] = [list(x) for x in self.top_untagged_services]
        return d


def build(lines: list[CostLine], tag_key: str = "CostCenter") -> Showback:
    months = sorted({l.month for l in lines})
    by_owner: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_service: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    totals: dict[str, float] = defaultdict(float)
    untagged_service: dict[str, float] = defaultdict(float)
    for l in lines:
        owner = l.tag_value or UNTAGGED
        by_owner[owner][l.month] += l.amount
        by_service[owner][l.service] += l.amount
        totals[l.month] += l.amount
        if not l.tag_value:
            untagged_service[l.service] += l.amount
    grand = sum(totals.values())
    untagged = sum(by_owner.get(UNTAGGED, {}).values())
    r2 = lambda d: {k: round(v, 2) for k, v in d.items()}
    order = sorted(by_owner, key=lambda o: (o == UNTAGGED, -sum(by_owner[o].values())))
    return Showback(
        tag_key=tag_key, months=months,
        by_owner={o: r2(by_owner[o]) for o in order},
        by_owner_service={o: r2(dict(sorted(by_service[o].items(), key=lambda kv: -kv[1]))) for o in order},
        totals=r2(totals),
        untagged_pct=round(100 * untagged / grand, 1) if grand else 0.0,
        top_untagged_services=[(s, round(v, 2)) for s, v in sorted(untagged_service.items(), key=lambda kv: -kv[1])[:5]],
    )


def collect(tag_key: str = "CostCenter", months: int = 3) -> list[CostLine]:  # pragma: no cover - needs AWS
    """Monthly unblended cost from Cost Explorer, grouped by the tag and by service."""
    import datetime as dt
    import boto3

    ce = boto3.client("ce", region_name="us-east-1")
    today = dt.date.today()
    first = today.replace(day=1)
    start = first
    for _ in range(months - 1):
        start = (start - dt.timedelta(days=1)).replace(day=1)
    out: list[CostLine] = []
    token = None
    while True:
        kw = dict(TimePeriod={"Start": start.isoformat(), "End": (today + dt.timedelta(days=1)).isoformat()},
                  Granularity="MONTHLY", Metrics=["UnblendedCost"],
                  GroupBy=[{"Type": "TAG", "Key": tag_key}, {"Type": "DIMENSION", "Key": "SERVICE"}])
        if token:
            kw["NextPageToken"] = token
        resp = ce.get_cost_and_usage(**kw)
        for period in resp["ResultsByTime"]:
            month = period["TimePeriod"]["Start"][:7]
            for g in period["Groups"]:
                tag, service = g["Keys"]
                value = tag.split("$", 1)[1] if "$" in tag else ""   # Cost Explorer returns "CostCenter$value"
                out.append(CostLine(month, value, service, float(g["Metrics"]["UnblendedCost"]["Amount"])))
        token = resp.get("NextPageToken")
        if not token:
            return out


def tag_compliance(region: str, required: list[str]) -> list[dict]:  # pragma: no cover - needs AWS
    """Resources missing any of the required tags (Resource Groups Tagging API)."""
    import boto3
    api = boto3.client("resourcegroupstaggingapi", region_name=region)
    missing = []
    for page in api.get_paginator("get_resources").paginate():
        for r in page["ResourceTagMappingList"]:
            tags = {t["Key"] for t in r.get("Tags", [])}
            gaps = [k for k in required if k not in tags]
            if gaps:
                missing.append({"arn": r["ResourceARN"], "missing": gaps})
    return missing
