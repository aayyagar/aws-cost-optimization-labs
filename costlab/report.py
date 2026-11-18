"""Self-contained HTML report (no external scripts), light and dark mode."""
from __future__ import annotations

import datetime as dt
import html

from . import __version__

e = lambda v: html.escape("" if v is None else str(v))
usd = lambda v: "-" if v is None else f"${v:,.0f}" if abs(v) >= 100 else f"${v:,.2f}"

CSS = """
:root{--bg:#f5f7fb;--surface:#fff;--ink:#14213d;--muted:#5b6478;--line:#dde3ec;--accent:#e07a1f;--ok:#1e8a5a;--warn:#b7791f;--bad:#c2362b;--bar:#2f6fd0;--bar2:#9aa3b5}
@media (prefers-color-scheme:dark){:root{--bg:#0f1420;--surface:#171e2e;--ink:#e8ecf4;--muted:#9aa3ba;--line:#283149;--accent:#ff9a3c;--ok:#4cc38a;--warn:#e8c04f;--bad:#ff6b5e;--bar:#5c97ff;--bar2:#56607a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Segoe UI",system-ui,-apple-system,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px}header{background:var(--surface);border-bottom:1px solid var(--line);padding:24px 0}
h1{margin:0;font-size:1.75rem}h2{margin:34px 0 6px;font-size:1.25rem}.sub,.note{color:var(--muted)}.note{font-size:.88rem;margin:0 0 10px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:20px 0}
.card{background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:12px;padding:12px 14px}
.card b{display:block;font-size:1.55rem;font-variant-numeric:tabular-nums}.card span{color:var(--muted);font-size:.85rem}
.tbl{background:var(--surface);border:1px solid var(--line);border-radius:12px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.86rem}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr:last-child td{border-bottom:0}.pill{display:inline-block;border-radius:999px;padding:1px 9px;font-size:.75rem;font-weight:600;border:1px solid currentColor}
.Idle,.Upsize{color:var(--bad)}.Burst-bound{color:var(--warn)}.Downsize{color:var(--ok)}.Keep{color:var(--muted)}
.bars{display:grid;gap:8px;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px}
.bar{display:grid;grid-template-columns:130px 1fr 90px;gap:10px;align-items:center;font-size:.86rem}
.track{height:14px;background:var(--line);border-radius:999px;overflow:hidden}.fill{height:100%;background:var(--bar)}.fill.u{background:var(--bar2)}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;align-items:start}footer{color:var(--muted);font-size:.8rem;padding:30px 0}
code{font-family:ui-monospace,Consolas,monospace;font-size:.85em}
"""


def _table(rows: list[list], head: list[str], numeric: set[int] = frozenset()) -> str:
    th = "".join(f"<th>{e(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f'<td class="n">{c}</td>' if i in numeric else f"<td>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="tbl"><table><thead><tr>{th}</tr></thead><tbody>{body or "<tr><td>Nothing found.</td></tr>"}</tbody></table></div>'


def render(result: dict, title: str = "AWS cost-optimization report") -> str:
    rs, sch, spot, sb, eks = (result.get(k) for k in ("rightsizing", "schedule", "spot", "showback", "eks"))
    cards, parts = [], []
    total = 0.0
    if rs is not None:
        s = sum(r["monthly_savings"] for r in rs if r["action"] in ("Downsize", "Idle"))
        total += s
        cards.append((usd(s), "per month from right-sizing and idle instances"))
        rows = [[f'{e(r["name"])}<br><code>{e(r["instance_id"])}</code>', e(r["owner"]), f'<code>{e(r["current_type"])}</code>',
                 f'<span class="pill {e(r["action"])}">{e(r["action"])}</span>', f'<code>{e(r["recommended_type"] or "-")}</code>',
                 e(r["cpu_p95"]), e("-" if r["mem_p95"] is None else r["mem_p95"]), usd(r["current_monthly"]), (usd(r["monthly_savings"]) if r["monthly_savings"] >= 0 else f"+{usd(-r['monthly_savings'])} cost"),
                 (f'<code>{e(r["graviton_type"])}</code> {usd(r["graviton_monthly_savings"])}' if r.get("graviton_type") and r.get("graviton_monthly_savings") else "-"),
                 e(r["reason"]) + "".join(f'<br><span class="note">{e(n)}</span>' for n in r["notes"])] for r in rs]
        parts.append('<h2>1. EC2 right-sizing</h2><p class="note">p95 CPU and memory over the look-back window, projected onto smaller sizes with AWS normalization factors. Downsize keeps projected p95 under 60% CPU (and under the credit baseline on T instances) and 75% memory. Graviton column: saving if you also move to Arm (test the workload first).</p>'
                     + _table(rows, ["Instance", "Owner", "Type", "Action", "Recommended", "CPU p95 %", "Mem p95 %", "Now / month", "Saving / month", "Graviton option", "Why"], {5, 6, 7, 8}))
    if sch is not None:
        s = sum(r["monthly_savings"] for r in sch)
        total += s
        cards.append((usd(s), "per month from scheduled shutdown"))
        rows = [[f'{e(r["name"])}<br><code>{e(r["instance_id"])}</code>', f'<code>{e(r["instance_type"])}</code>', e(r["schedule"]), e(r["hours_per_week"]),
                 usd(r["always_on_monthly"]), usd(r["scheduled_monthly"]), usd(r["monthly_savings"])] for r in sch]
        parts.append('<h2>2a. Scheduled shutdown</h2><p class="note">Instances tagged <code>Schedule</code> run only during their schedule (office-hours = 07:00-19:00 Mon-Fri, 60 of 168 hours).</p>'
                     + _table(rows, ["Instance", "Type", "Schedule", "Hours / week", "Always on", "Scheduled", "Saving / month"], {3, 4, 5, 6}))
    if spot is not None:
        rows = [[f'<code>{e(q["instance_type"])}</code>', f'${q["on_demand_hourly"]:.4f}', f'${q["spot_hourly"]:.4f}', f'{q["discount_pct"]:.0f}%', usd(q["monthly_savings_per_instance"]), e(q["source"])] for q in spot]
        parts.append('<h2>2b. Spot versus On-Demand</h2><p class="note">Per-instance saving for interruption-tolerant capacity (stateless web tiers, CI runners, batch). Use several instance types and the price-capacity-optimized strategy to keep interruptions rare.</p>'
                     + _table(rows, ["Type", "On-Demand / h", "Spot / h", "Discount", "Saving / instance / month", "Spot price source"], {1, 2, 3, 4}))
    if sb is not None:
        last = sb["months"][-1]
        top = max((v.get(last, 0) for v in sb["by_owner"].values()), default=1) or 1
        bars = "".join(f'<div class="bar"><span>{e(o)}</span><div class="track"><div class="fill{" u" if o.startswith("(") else ""}" style="width:{100 * m.get(last, 0) / top:.1f}%"></div></div><span class="n">{usd(m.get(last, 0))}</span></div>' for o, m in sb["by_owner"].items())
        rows = [[e(o)] + [usd(m.get(mo, 0)) for mo in sb["months"]] + [", ".join(f"{e(s)} {usd(v)}" for s, v in list(sb["by_owner_service"][o].items())[:3])] for o, m in sb["by_owner"].items()]
        rows.append(["<b>Total</b>"] + [f"<b>{usd(sb['totals'][mo])}</b>" for mo in sb["months"]] + [""])
        trend = " → ".join(f"{mo}: {100 * sb['by_owner'].get('(untagged)', {}).get(mo, 0) / sb['totals'][mo]:.0f}%" for mo in sb["months"]) if sb["totals"] else ""
        cards.append((f'{sb["untagged_pct"]:.0f}%', f'of spend has no {e(sb["tag_key"])} tag'))
        parts.append(f'<h2>3. Showback by {e(sb["tag_key"])}</h2><p class="note">What each team spent, from Cost Explorer grouped by the cost-allocation tag. Untagged share by month: {e(trend)}. Largest untagged services: {e(", ".join(f"{s} {usd(v)}" for s, v in sb["top_untagged_services"]))}.</p>'
                     + f'<div class="two"><div class="bars"><b>{e(last)}</b>{bars}</div>' + _table(rows, ["Owner"] + sb["months"] + ["Top services"], set(range(1, len(sb["months"]) + 1))) + "</div>")
    if eks is not None:
        b, a = eks["before"], eks["after"]
        s = round(b["monthly"] - a["monthly"], 2)
        total += s
        cards.append((usd(s), "per month on EKS nodes with Karpenter"))
        row = lambda label, c: [e(label), e(c["nodes"]), e(c["spot_nodes"]), f'{c["requested_cpu_pct"]}%', usd(c["monthly"]), e(", ".join(f"{k} x{v}" for k, v in c["by_type"].items()))]
        parts.append('<h2>4. EKS autoscaling with Karpenter</h2><p class="note">The same workload on a fixed On-Demand node group, then after Karpenter right-sized nodes per pod, consolidated under-used ones and moved interruption-tolerant pods to Spot.</p>'
                     + _table([row("Before (node group)", b), row("After (Karpenter)", a)], ["Cluster", "Nodes", "Spot", "CPU requested", "Monthly", "Nodes by type"], {1, 2, 3, 4}))
    cards.insert(0, (usd(total), "estimated monthly saving in total"))
    card_html = "".join(f"<div class=\"card\"><b>{v}</b><span>{l}</span></div>" for v, l in cards)
    meta = result.get("meta", {})
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><style>{CSS}</style></head><body>
<header><div class="wrap"><h1>{e(title)}</h1><div class="sub">{e(meta.get("account", ""))} · {e(meta.get("region", ""))} · generated {dt.datetime.now().strftime("%Y-%m-%d %H:%M")}</div></div></header>
<main class="wrap"><div class="cards">{card_html}</div>{"".join(parts)}
<p class="note" style="margin-top:28px">Estimates use us-east-1 Linux On-Demand list prices unless live pricing was requested. Savings are before Savings Plans or Reserved Instances, which apply on top of right-sizing - right-size first, then commit.</p></main>
<footer class="wrap">costlab v{__version__} · aws-cost-optimization-labs · MIT License</footer></body></html>"""
