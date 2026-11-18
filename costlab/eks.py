"""Lab 4 - EKS node cost with Karpenter.

Prices the nodes in a cluster (from `kubectl get nodes -o json`) by instance type and capacity
type, so you can compare the cluster before and after Karpenter consolidation and Spot.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict

from . import pricing

SPOT_DISCOUNT_ASSUMED = 0.65   # used only when no Spot price is supplied


@dataclass
class Node:
    name: str
    instance_type: str
    capacity_type: str   # on-demand | spot
    managed_by: str      # karpenter | node-group
    cpu: float
    cpu_requested: float = 0.0


@dataclass
class NodeCost:
    nodes: int
    spot_nodes: int
    hourly: float
    monthly: float
    by_type: dict[str, int]
    requested_cpu_pct: float

    def to_dict(self) -> dict:
        return asdict(self)


def price_nodes(nodes: list[Node], spot_prices: dict[str, float] | None = None, prices=None) -> NodeCost:
    hourly = 0.0
    by_type: dict[str, int] = {}
    for n in nodes:
        od = pricing.hourly_price(n.instance_type, prices) or 0
        if n.capacity_type == "spot":
            hourly += (spot_prices or {}).get(n.instance_type, od * (1 - SPOT_DISCOUNT_ASSUMED))
        else:
            hourly += od
        key = f"{n.instance_type} ({n.capacity_type})"
        by_type[key] = by_type.get(key, 0) + 1
    cpu = sum(n.cpu for n in nodes)
    req = sum(n.cpu_requested for n in nodes)
    return NodeCost(len(nodes), sum(1 for n in nodes if n.capacity_type == "spot"), round(hourly, 4),
                    pricing.monthly(hourly), dict(sorted(by_type.items())), round(100 * req / cpu, 1) if cpu else 0.0)


def _cpu(v: str) -> float:
    return float(v[:-1]) / 1000 if v.endswith("m") else float(v)


def from_kubectl(context: str | None = None) -> list[Node]:  # pragma: no cover - needs a cluster
    cmd = ["kubectl", "get", "nodes", "-o", "json"] + (["--context", context] if context else [])
    data = json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)
    pods_cmd = ["kubectl", "get", "pods", "-A", "-o", "json", "--field-selector=status.phase=Running"] + (["--context", context] if context else [])
    pods = json.loads(subprocess.run(pods_cmd, check=True, capture_output=True, text=True).stdout)
    requested: dict[str, float] = {}
    for p in pods["items"]:
        node = p["spec"].get("nodeName")
        for c in p["spec"].get("containers", []):
            r = c.get("resources", {}).get("requests", {}).get("cpu")
            if node and r:
                requested[node] = requested.get(node, 0) + _cpu(r)
    out = []
    for n in data["items"]:
        lab = n["metadata"].get("labels", {})
        name = n["metadata"]["name"]
        cap = lab.get("karpenter.sh/capacity-type") or ("spot" if lab.get("eks.amazonaws.com/capacityType") == "SPOT" else "on-demand")
        out.append(Node(name, lab.get("node.kubernetes.io/instance-type", "unknown"), cap,
                        "karpenter" if "karpenter.sh/nodepool" in lab else "node-group",
                        _cpu(n["status"]["capacity"]["cpu"]), requested.get(name, 0.0)))
    return out


# Demo: the same workload before (static on-demand node group) and after Karpenter (consolidated, mostly Spot).
DEMO_BEFORE = [Node(f"ip-10-0-1-{i}", "m5.2xlarge", "on-demand", "node-group", 8, c) for i, c in enumerate([3.1, 2.4, 1.8, 2.9, 1.2, 0.9], 10)]
DEMO_AFTER = [Node("ip-10-0-2-10", "m5.large", "on-demand", "node-group", 2, 0.6), Node("ip-10-0-2-11", "m5.large", "on-demand", "node-group", 2, 0.5),
              Node("ip-10-0-3-20", "c6i.2xlarge", "spot", "karpenter", 8, 7.4), Node("ip-10-0-3-21", "m6i.xlarge", "spot", "karpenter", 4, 3.8)]
