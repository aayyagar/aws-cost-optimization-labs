"""Lab 2 - scheduled shutdown and Spot.

Scheduled shutdown: instances tagged Schedule=<name> only need to run during the hours the
schedule allows. Spot: the same capacity on spare EC2 at a discount, for workloads that can
take a two-minute interruption notice.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from . import pricing

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class Schedule:
    name: str
    start_hour: int        # local time the instances start
    stop_hour: int         # local time they stop
    days: tuple[str, ...]  # days the schedule runs on

    @property
    def hours_per_week(self) -> float:
        per_day = (self.stop_hour - self.start_hour) % 24 or 24
        return per_day * len(self.days)

    @property
    def running_fraction(self) -> float:
        return self.hours_per_week / 168


OFFICE_HOURS = Schedule("office-hours", 7, 19, ("Mon", "Tue", "Wed", "Thu", "Fri"))
SCHEDULES = {OFFICE_HOURS.name: OFFICE_HOURS, "extended-hours": Schedule("extended-hours", 6, 22, ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat"))}


def parse_schedule(text: str) -> Schedule:
    """'office-hours', or 'name:07-19:Mon-Fri' / 'name:08-18:Mon,Wed,Fri'."""
    if text in SCHEDULES:
        return SCHEDULES[text]
    name, hours, days = text.split(":")
    a, b = (int(x) for x in hours.split("-"))
    if "-" in days:
        d1, d2 = days.split("-")
        chosen = tuple(DAYS[DAYS.index(d1): DAYS.index(d2) + 1])
    else:
        chosen = tuple(d.strip() for d in days.split(","))
    for d in chosen:
        if d not in DAYS:
            raise ValueError(f"unknown day {d!r}")
    if not (0 <= a <= 23 and 0 <= b <= 23):
        raise ValueError("hours must be 0-23")
    return Schedule(name, a, b, chosen)


@dataclass
class ScheduleSaving:
    instance_id: str
    name: str
    instance_type: str
    schedule: str
    hours_per_week: float
    always_on_monthly: float
    scheduled_monthly: float
    monthly_savings: float

    def to_dict(self) -> dict:
        return asdict(self)


def schedule_saving(instance_id: str, name: str, instance_type: str, sched: Schedule, prices=None) -> ScheduleSaving:
    p = pricing.hourly_price(instance_type, prices) or 0
    always = pricing.monthly(p)
    scheduled = round(always * sched.running_fraction, 2)
    return ScheduleSaving(instance_id, name, instance_type, sched.name, sched.hours_per_week, always, scheduled, round(always - scheduled, 2))


@dataclass
class SpotQuote:
    instance_type: str
    on_demand_hourly: float
    spot_hourly: float
    discount_pct: float
    monthly_savings_per_instance: float
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


def spot_quote(instance_type: str, spot_hourly: float, source: str, prices=None) -> SpotQuote | None:
    od = pricing.hourly_price(instance_type, prices)
    if not od:
        return None
    return SpotQuote(instance_type, od, round(spot_hourly, 4), round((1 - spot_hourly / od) * 100, 1),
                     round(pricing.monthly(od) - pricing.monthly(spot_hourly), 2), source)


def collect_tagged(region: str, tag_key: str = "Schedule"):  # pragma: no cover - needs AWS
    import boto3
    ec2 = boto3.client("ec2", region_name=region)
    out = []
    for page in ec2.get_paginator("describe_instances").paginate(
            Filters=[{"Name": "tag-key", "Values": [tag_key]}, {"Name": "instance-state-name", "Values": ["running", "stopped"]}]):
        for res in page["Reservations"]:
            for i in res["Instances"]:
                tags = {t["Key"]: t["Value"] for t in i.get("Tags", [])}
                out.append((i["InstanceId"], tags.get("Name", ""), i["InstanceType"], tags[tag_key]))
    return out


def spot_prices(region: str, instance_types: list[str]) -> dict[str, float]:  # pragma: no cover - needs AWS
    """Lowest current Linux Spot price across the region's AZs."""
    import datetime as dt
    import boto3
    ec2 = boto3.client("ec2", region_name=region)
    resp = ec2.describe_spot_price_history(InstanceTypes=instance_types, ProductDescriptions=["Linux/UNIX"],
                                           StartTime=dt.datetime.now(dt.timezone.utc))
    best: dict[str, float] = {}
    for p in resp["SpotPriceHistory"]:
        v = float(p["SpotPrice"])
        best[p["InstanceType"]] = min(v, best.get(p["InstanceType"], v))
    return best
