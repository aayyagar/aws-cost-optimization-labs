"""On-demand prices used for estimates, and EC2 size arithmetic.

Prices are us-east-1 Linux On-Demand list prices (USD per hour) for the `large` size of each
family. Within these families AWS prices scale linearly with size, so every other size is
derived from AWS's normalization factors (nano 0.25 ... 2xlarge 16). Use `--live-pricing` to
look prices up with the AWS Pricing API instead.
"""
from __future__ import annotations

HOURS_PER_MONTH = 730

LARGE_PRICE = {
    "t3": 0.0832, "t3a": 0.0752, "t4g": 0.0672,
    "m5": 0.096, "m5a": 0.086, "m6i": 0.096, "m6a": 0.0864, "m7i": 0.1008, "m7g": 0.0816,
    "c5": 0.085, "c6i": 0.085, "c6a": 0.0765, "c7g": 0.0725,
    "r5": 0.126, "r6i": 0.126, "r6a": 0.1134, "r7g": 0.1071,
}

SIZES = ["nano", "micro", "small", "medium", "large", "xlarge", "2xlarge", "4xlarge", "8xlarge", "12xlarge", "16xlarge"]
NORMALIZATION = {"nano": 0.25, "micro": 0.5, "small": 1, "medium": 2, "large": 4, "xlarge": 8,
                 "2xlarge": 16, "4xlarge": 32, "8xlarge": 64, "12xlarge": 96, "16xlarge": 128}

# Smallest and largest size offered per family (keeps recommendations real).
FAMILY_RANGE = {
    "t3": ("nano", "2xlarge"), "t3a": ("nano", "2xlarge"), "t4g": ("nano", "2xlarge"),
    "m7g": ("medium", "16xlarge"), "c7g": ("medium", "16xlarge"), "r7g": ("medium", "16xlarge"),
}
DEFAULT_RANGE = ("large", "16xlarge")

GRAVITON = {"t3": "t4g", "t3a": "t4g", "m5": "m7g", "m5a": "m7g", "m6i": "m7g", "m6a": "m7g", "m7i": "m7g",
            "c5": "c7g", "c6i": "c7g", "c6a": "c7g", "r5": "r7g", "r6i": "r7g", "r6a": "r7g"}


# vCPUs and memory. Burstable families have 2 vCPUs from nano to large, so CPU and memory
# have to be projected separately; fixed-performance families scale both with size.
BURSTABLE = {"t3", "t3a", "t4g"}
T_VCPU = {"nano": 2, "micro": 2, "small": 2, "medium": 2, "large": 2, "xlarge": 4, "2xlarge": 8}
T_MEM = {"nano": 0.5, "micro": 1, "small": 2, "medium": 4, "large": 8, "xlarge": 16, "2xlarge": 32}
# Baseline CPU per vCPU a T3/T3a/T4g can sustain without spending credits (percent).
T_BASELINE = {"nano": 5, "micro": 10, "small": 20, "medium": 20, "large": 30, "xlarge": 40, "2xlarge": 40}
MEM_PER_VCPU = {"m": 4, "c": 2, "r": 8}


def split(instance_type: str) -> tuple[str, str]:
    family, _, size = instance_type.partition(".")
    return family, size


def sizes_for(family: str) -> list[str]:
    lo, hi = FAMILY_RANGE.get(family, DEFAULT_RANGE)
    return SIZES[SIZES.index(lo): SIZES.index(hi) + 1]


def known(instance_type: str) -> bool:
    family, size = split(instance_type)
    return family in LARGE_PRICE and size in sizes_for(family)


def hourly_price(instance_type: str, overrides: dict[str, float] | None = None) -> float | None:
    if overrides and instance_type in overrides:
        return overrides[instance_type]
    family, size = split(instance_type)
    if not known(instance_type):
        return None
    return round(LARGE_PRICE[family] * NORMALIZATION[size] / 4, 4)


def monthly(price_per_hour: float | None, hours: float = HOURS_PER_MONTH) -> float:
    return round((price_per_hour or 0) * hours, 2)


def step(instance_type: str, delta: int) -> str | None:
    """The size `delta` steps up (+) or down (-) in the same family, or None at the edge."""
    family, size = split(instance_type)
    order = sizes_for(family)
    if size not in order:
        return None
    i = order.index(size) + delta
    return f"{family}.{order[i]}" if 0 <= i < len(order) else None


def capacity_ratio(from_type: str, to_type: str) -> float:
    """How much more (>1) or less (<1) capacity to_type has than from_type, by normalization factor."""
    return NORMALIZATION[split(to_type)[1]] / NORMALIZATION[split(from_type)[1]]


def vcpus(instance_type: str) -> float:
    family, size = split(instance_type)
    if family in BURSTABLE:
        return T_VCPU[size]
    return NORMALIZATION[size] / 2          # large = 2 vCPU, xlarge = 4, ...


def memory_gib(instance_type: str) -> float:
    family, size = split(instance_type)
    if family in BURSTABLE:
        return T_MEM[size]
    return vcpus(instance_type) * MEM_PER_VCPU.get(family[0], 4)


def burst_baseline(instance_type: str) -> float | None:
    family, size = split(instance_type)
    return T_BASELINE.get(size) if family in BURSTABLE else None


def graviton_equivalent(instance_type: str) -> str | None:
    family, size = split(instance_type)
    g = GRAVITON.get(family)
    if not g:
        return None
    candidate = f"{g}.{size}"
    return candidate if known(candidate) else None


def live_prices(instance_types: list[str], region: str) -> dict[str, float]:  # pragma: no cover - needs AWS
    """Look up Linux On-Demand prices with the AWS Pricing API (endpoint is in us-east-1)."""
    import json
    import boto3

    location = _REGION_NAMES.get(region)
    if not location:
        raise ValueError(f"Add {region} to _REGION_NAMES to use live pricing")
    client = boto3.client("pricing", region_name="us-east-1")
    out: dict[str, float] = {}
    for t in sorted(set(instance_types)):
        resp = client.get_products(ServiceCode="AmazonEC2", MaxResults=1, Filters=[
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": t},
            {"Type": "TERM_MATCH", "Field": "location", "Value": location},
            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
            {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
            {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
            {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
        ])
        for item in resp.get("PriceList", []):
            terms = json.loads(item)["terms"]["OnDemand"]
            dim = next(iter(next(iter(terms.values()))["priceDimensions"].values()))
            out[t] = float(dim["pricePerUnit"]["USD"])
    return out


_REGION_NAMES = {
    "us-east-1": "US East (N. Virginia)", "us-east-2": "US East (Ohio)", "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)", "ca-central-1": "Canada (Central)", "eu-west-1": "EU (Ireland)",
    "eu-west-2": "EU (London)", "eu-central-1": "EU (Frankfurt)", "ap-south-1": "Asia Pacific (Mumbai)",
    "ap-southeast-1": "Asia Pacific (Singapore)", "ap-southeast-2": "Asia Pacific (Sydney)", "ap-northeast-1": "Asia Pacific (Tokyo)",
}
