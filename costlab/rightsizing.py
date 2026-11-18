"""Lab 1 - EC2 right-sizing.

For every running instance, take the 95th percentile of CPU (and memory, when the CloudWatch
agent publishes it) over the look-back window and recommend the size that keeps p95 under the
target, using AWS normalization factors to project utilization on another size. Idle
instances are flagged to stop, and a Graviton equivalent is suggested as a further saving.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field

from . import pricing

TARGET_CPU = 60.0      # projected p95 CPU must stay at or below this after a downsize
TARGET_MEM = 75.0      # projected p95 memory must stay at or below this after a downsize
UPSIZE_CPU = 85.0      # p95 above this means the instance is too small
UPSIZE_MEM = 90.0
IDLE_CPU_MAX = 5.0     # max CPU below this for the whole window = idle


@dataclass
class Usage:
    instance_id: str
    name: str
    instance_type: str
    cpu_p95: float
    cpu_max: float
    mem_p95: float | None = None
    owner: str = ""
    days: int = 14


@dataclass
class Recommendation:
    instance_id: str
    name: str
    owner: str
    current_type: str
    action: str            # Idle | Downsize | Upsize | Burst-bound | Keep | Unknown type
    recommended_type: str | None
    cpu_p95: float
    mem_p95: float | None
    projected_cpu_p95: float | None
    current_monthly: float
    recommended_monthly: float
    monthly_savings: float
    graviton_type: str | None = None
    graviton_monthly_savings: float | None = None
    reason: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def recommend(u: Usage, prices: dict[str, float] | None = None) -> Recommendation:
    cur_price = pricing.hourly_price(u.instance_type, prices)
    base = dict(instance_id=u.instance_id, name=u.name, owner=u.owner, current_type=u.instance_type,
                cpu_p95=round(u.cpu_p95, 1), mem_p95=None if u.mem_p95 is None else round(u.mem_p95, 1))
    if cur_price is None:
        return Recommendation(**base, action="Unknown type", recommended_type=None, projected_cpu_p95=None,
                              current_monthly=0, recommended_monthly=0, monthly_savings=0,
                              reason=f"{u.instance_type} is not in the price table; pass --live-pricing")
    cur_month = pricing.monthly(cur_price)
    notes = [] if u.mem_p95 is not None else ["No memory data: install the CloudWatch agent for a safer recommendation"]

    if u.cpu_max < IDLE_CPU_MAX:
        return Recommendation(**base, action="Idle", recommended_type=None, projected_cpu_p95=None,
                              current_monthly=cur_month, recommended_monthly=0, monthly_savings=cur_month,
                              reason=f"CPU never went above {u.cpu_max:.1f}% in {u.days} days: stop it, or terminate it after a snapshot",
                              notes=notes)

    baseline = pricing.burst_baseline(u.instance_type)
    if baseline is not None and u.cpu_p95 > baseline and u.cpu_p95 <= UPSIZE_CPU:
        notes.append(f"Runs above its {baseline:.0f}% CPU-credit baseline: in unlimited mode you pay for surplus credits")
        alt = _fixed_performance(u.instance_type)
        return Recommendation(**base, action="Burst-bound", recommended_type=alt, projected_cpu_p95=None,
                              current_monthly=cur_month, recommended_monthly=pricing.monthly(pricing.hourly_price(alt, prices)) if alt else cur_month,
                              monthly_savings=0,
                              reason=f"p95 CPU {u.cpu_p95:.0f}% is above the {baseline:.0f}% a {u.instance_type} sustains; move to a fixed-performance type"
                                     + (f" such as {alt}" if alt else ""),
                              notes=notes)

    if u.cpu_p95 > UPSIZE_CPU or (u.mem_p95 or 0) > UPSIZE_MEM:
        bigger = pricing.step(u.instance_type, +1)
        new_price = pricing.hourly_price(bigger, prices) if bigger else None
        return Recommendation(**base, action="Upsize", recommended_type=bigger,
                              projected_cpu_p95=round(u.cpu_p95 * pricing.vcpus(u.instance_type) / pricing.vcpus(bigger), 1) if bigger else None,
                              current_monthly=cur_month, recommended_monthly=pricing.monthly(new_price) if bigger else cur_month,
                              monthly_savings=round(cur_month - pricing.monthly(new_price), 2) if bigger else 0,
                              reason="p95 utilization is above the safe ceiling; performance is at risk", notes=notes)

    # Walk down one size at a time while the projection stays under the targets.
    def project(target: str) -> tuple[float, float | None]:
        cpu = u.cpu_p95 * pricing.vcpus(u.instance_type) / pricing.vcpus(target)
        mem = None if u.mem_p95 is None else u.mem_p95 * pricing.memory_gib(u.instance_type) / pricing.memory_gib(target)
        return cpu, mem

    best = u.instance_type
    while True:
        smaller = pricing.step(best, -1)
        if not smaller:
            break
        cpu_proj, mem_proj = project(smaller)
        cpu_limit = TARGET_CPU
        b = pricing.burst_baseline(smaller)
        if b is not None:
            cpu_limit = min(cpu_limit, b)       # a T instance must stay under its credit baseline
        if cpu_proj > cpu_limit or (mem_proj is not None and mem_proj > TARGET_MEM):
            break
        if u.mem_p95 is None and pricing.memory_gib(smaller) < pricing.memory_gib(u.instance_type) / 2:
            break  # without memory data, never more than halve the memory
        best = smaller

    g = pricing.graviton_equivalent(best)
    g_save = None
    if g:
        g_save = round(pricing.monthly(cur_price) - pricing.monthly(pricing.hourly_price(g, prices)), 2)

    if best == u.instance_type:
        return Recommendation(**base, action="Keep", recommended_type=u.instance_type, projected_cpu_p95=round(u.cpu_p95, 1),
                              current_monthly=cur_month, recommended_monthly=cur_month, monthly_savings=0,
                              graviton_type=g, graviton_monthly_savings=g_save if g_save and g_save > 0 else None,
                              reason="Sized correctly for its p95 load", notes=notes)
    new_month = pricing.monthly(pricing.hourly_price(best, prices))
    return Recommendation(**base, action="Downsize", recommended_type=best,
                          projected_cpu_p95=round(project(best)[0], 1),
                          current_monthly=cur_month, recommended_monthly=new_month, monthly_savings=round(cur_month - new_month, 2),
                          graviton_type=g, graviton_monthly_savings=g_save,
                          reason=f"p95 CPU {u.cpu_p95:.0f}% would be about {project(best)[0]:.0f}% on {best}"
                                 + ("" if project(best)[1] is None else f", memory about {project(best)[1]:.0f}%"),
                          notes=notes)


def _fixed_performance(instance_type: str) -> str | None:
    """The cheapest m7i/m7g size with at least as many vCPUs and as much memory."""
    need_cpu, need_mem = pricing.vcpus(instance_type), pricing.memory_gib(instance_type)
    family, _ = pricing.split(instance_type)
    target = "m7g" if family == "t4g" else "m7i"
    for size in pricing.sizes_for(target):
        cand = f"{target}.{size}"
        if pricing.vcpus(cand) >= need_cpu and pricing.memory_gib(cand) >= need_mem:
            return cand
    return None


def collect(region: str, days: int = 14) -> list[Usage]:  # pragma: no cover - needs AWS
    """Read running instances and their CloudWatch CPU / memory percentiles."""
    import datetime as dt
    import boto3

    ec2 = boto3.client("ec2", region_name=region)
    cw = boto3.client("cloudwatch", region_name=region)
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=days)
    out: list[Usage] = []

    def stat(namespace, metric, dims, extended=None, plain=None):
        kw = dict(Namespace=namespace, MetricName=metric, Dimensions=dims, StartTime=start, EndTime=end, Period=86400 * days)
        if extended:
            kw["ExtendedStatistics"] = [extended]
        else:
            kw["Statistics"] = [plain]
        pts = cw.get_metric_statistics(**kw)["Datapoints"]
        if not pts:
            return None
        return pts[0]["ExtendedStatistics"][extended] if extended else pts[0][plain]

    for page in ec2.get_paginator("describe_instances").paginate(Filters=[{"Name": "instance-state-name", "Values": ["running"]}]):
        for res in page["Reservations"]:
            for i in res["Instances"]:
                tags = {t["Key"]: t["Value"] for t in i.get("Tags", [])}
                dims = [{"Name": "InstanceId", "Value": i["InstanceId"]}]
                cpu95 = stat("AWS/EC2", "CPUUtilization", dims, extended="p95")
                cpumax = stat("AWS/EC2", "CPUUtilization", dims, plain="Maximum")
                if cpu95 is None:
                    continue
                mem = stat("CWAgent", "mem_used_percent", dims, extended="p95")
                out.append(Usage(i["InstanceId"], tags.get("Name", ""), i["InstanceType"], cpu95, cpumax or cpu95, mem,
                                 tags.get("Owner", ""), days))
    return out
