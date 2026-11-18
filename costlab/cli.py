"""Command line: python -m costlab <command> [--demo] [--html FILE] [--json FILE]."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, demo, eks, pricing, report, rightsizing, scheduling, showback


def _rightsizing(args) -> list[dict]:
    usage = demo.USAGE if args.demo else rightsizing.collect(args.region, args.days)
    prices = None
    if args.live_pricing and not args.demo:
        types = {u.instance_type for u in usage}
        types |= {t for u in usage for t in (pricing.step(u.instance_type, d) for d in (-3, -2, -1, 1)) if t}
        types |= {g for t in list(types) if (g := pricing.graviton_equivalent(t))}
        prices = pricing.live_prices(sorted(types), args.region)
    recs = [rightsizing.recommend(u, prices) for u in usage]
    order = {"Idle": 0, "Downsize": 1, "Upsize": 2, "Burst-bound": 3, "Keep": 4, "Unknown type": 5}
    return [r.to_dict() for r in sorted(recs, key=lambda r: (order[r.action], -r.monthly_savings))]


def _schedule(args) -> list[dict]:
    rows = demo.SCHEDULED if args.demo else scheduling.collect_tagged(args.region, args.tag_key)
    out = []
    for iid, name, itype, tag in rows:
        try:
            sched = scheduling.parse_schedule(tag)
        except ValueError:
            print(f"  skipping {iid}: unknown schedule {tag!r}", file=sys.stderr)
            continue
        out.append(scheduling.schedule_saving(iid, name, itype, sched).to_dict())
    return out


def _spot(args) -> list[dict]:
    types = args.types or sorted(demo.SPOT)
    if args.demo:
        prices, source = {t: demo.SPOT[t] for t in types if t in demo.SPOT}, "illustrative (demo)"
    else:
        prices, source = scheduling.spot_prices(args.region, types), f"describe-spot-price-history, lowest AZ in {args.region}"
    return [q.to_dict() for t in types if t in prices and (q := scheduling.spot_quote(t, prices[t], source))]


def _showback(args) -> dict:
    lines = demo.cost_lines() if args.demo else showback.collect(args.tag_key, args.months)
    return showback.build(lines, args.tag_key).to_dict()


def _eks(args) -> dict:
    if args.demo:
        return {"before": eks.price_nodes(eks.DEMO_BEFORE).to_dict(), "after": eks.price_nodes(eks.DEMO_AFTER).to_dict()}
    nodes = eks.from_kubectl(args.context)
    cost = eks.price_nodes(nodes).to_dict()
    return {"before": cost, "after": cost}


def _print(cmd: str, data) -> None:
    if cmd == "rightsize":
        for r in data:
            v = r['monthly_savings']
            money = f"save ${v:,.2f}/mo" if v > 0 else (f"costs ${-v:,.2f}/mo more" if v < 0 else "")
            print(f"  [{r['action']:<11}] {r['name'] or r['instance_id']:<20} {r['current_type']:<12} -> {r['recommended_type'] or '-':<12} {money}")
        print(f"\n  Potential saving: ${sum(r['monthly_savings'] for r in data if r['action'] in ('Downsize', 'Idle')):,.2f} per month")
    elif cmd == "schedule":
        for r in data:
            print(f"  {r['name'] or r['instance_id']:<20} {r['instance_type']:<12} {r['schedule']:<15} save ${r['monthly_savings']:,.2f}/mo")
        print(f"\n  Saving: ${sum(r['monthly_savings'] for r in data):,.2f} per month")
    elif cmd == "spot":
        for q in data:
            print(f"  {q['instance_type']:<12} on-demand ${q['on_demand_hourly']:.4f}/h  spot ${q['spot_hourly']:.4f}/h  ({q['discount_pct']:.0f}% off)")
    elif cmd == "showback":
        last = data["months"][-1]
        for owner, months in data["by_owner"].items():
            print(f"  {owner:<14} ${months.get(last, 0):>10,.2f}  ({last})")
        print(f"\n  Untagged: {data['untagged_pct']}% of spend")
    elif cmd == "eks":
        b, a = data["before"], data["after"]
        print(f"  before: {b['nodes']} nodes ${b['monthly']:,.2f}/mo   after: {a['nodes']} nodes ({a['spot_nodes']} Spot) ${a['monthly']:,.2f}/mo")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="costlab", description="Analysis tools for the AWS cost-optimization labs (read-only).")
    ap.add_argument("--version", action="version", version=f"costlab {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--demo", action="store_true", help="use the built-in fictional account (no AWS credentials needed)")
        p.add_argument("--region", default="us-east-1")
        p.add_argument("--html", help="write an HTML report")
        p.add_argument("--json", dest="json_out", help="write the results as JSON")
        return p

    p = common(sub.add_parser("rightsize", help="Lab 1: right-size running EC2 instances from CloudWatch"))
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--live-pricing", action="store_true", help="look prices up with the AWS Pricing API")
    p = common(sub.add_parser("schedule", help="Lab 2: savings from instances tagged with a Schedule"))
    p.add_argument("--tag-key", default="Schedule")
    p = common(sub.add_parser("spot", help="Lab 2: current Spot discount for instance types"))
    p.add_argument("--types", nargs="*")
    p = common(sub.add_parser("showback", help="Lab 3: cost per owner from a cost-allocation tag"))
    p.add_argument("--tag-key", default="CostCenter")
    p.add_argument("--months", type=int, default=3)
    p = common(sub.add_parser("eks", help="Lab 4: price the nodes of the current kubectl cluster"))
    p.add_argument("--context")
    p = common(sub.add_parser("report", help="run every analysis and write one report"))
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--live-pricing", action="store_true")
    p.add_argument("--types", nargs="*")
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--context")
    p.add_argument("--skip", nargs="*", default=[], choices=["rightsize", "schedule", "spot", "showback", "eks"])
    args = ap.parse_args(argv)

    run = {"rightsize": _rightsizing, "schedule": _schedule, "spot": _spot, "showback": _showback, "eks": _eks}
    key = {"rightsize": "rightsizing", "schedule": "schedule", "spot": "spot", "showback": "showback", "eks": "eks"}
    result: dict = {"meta": {"account": "Demo account (fictional)" if args.demo else "AWS account", "region": args.region}}
    cmds = [c for c in run if c not in args.skip] if args.cmd == "report" else [args.cmd]
    if args.cmd == "report":
        for attr, default in (("tag_key", None), ("types", None)):
            if not hasattr(args, attr):
                setattr(args, attr, default)
    for c in cmds:
        if c == "schedule" and getattr(args, "tag_key", None) in (None, "CostCenter"):
            args.tag_key = "Schedule"
        if c == "showback":
            args.tag_key = "CostCenter" if args.cmd == "report" else args.tag_key
        try:
            data = run[c](args)
        except Exception as ex:  # keep the other analyses going in a report
            if args.cmd != "report":
                raise
            print(f"  {c}: skipped ({ex})", file=sys.stderr)
            continue
        result[key[c]] = data
        print(f"\n== {c}")
        _print(c, data)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\n  JSON: {args.json_out}")
    if args.html:
        Path(args.html).parent.mkdir(parents=True, exist_ok=True)
        Path(args.html).write_text(report.render(result), encoding="utf-8")
        print(f"  HTML: {args.html}")
    return 0
