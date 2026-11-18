import json
import subprocess
import sys
from pathlib import Path

import pytest

from costlab import demo, eks, pricing, report, rightsizing, scheduling, showback
from costlab.rightsizing import Usage

ROOT = Path(__file__).resolve().parents[1]


def test_prices_scale_with_normalization_factors():
    assert pricing.hourly_price("m6i.large") == 0.096
    assert pricing.hourly_price("m6i.2xlarge") == 0.384
    assert pricing.hourly_price("t3.micro") == 0.0104
    assert pricing.hourly_price("m6i.micro") is None          # size the family does not offer
    assert pricing.hourly_price("x2iedn.large") is None       # family not in the table
    assert pricing.hourly_price("x2iedn.large", {"x2iedn.large": 1.0}) == 1.0


def test_size_steps_stay_inside_the_family():
    assert pricing.step("m6i.xlarge", -1) == "m6i.large"
    assert pricing.step("m6i.large", -1) is None
    assert pricing.step("m7g.large", -1) == "m7g.medium"
    assert pricing.step("t3.nano", -1) is None
    assert pricing.graviton_equivalent("m6i.xlarge") == "m7g.xlarge"
    assert pricing.graviton_equivalent("t3.nano") == "t4g.nano"
    assert pricing.graviton_equivalent("m7g.large") is None


def test_idle_instance_is_flagged_with_full_saving():
    r = rightsizing.recommend(Usage("i-1", "old", "m5.xlarge", 0.8, 2.6, 10))
    assert r.action == "Idle"
    assert r.monthly_savings == pricing.monthly(pricing.hourly_price("m5.xlarge"))


def test_downsize_stops_at_the_memory_limit():
    r = rightsizing.recommend(Usage("i-2", "batch", "c6i.4xlarge", 9, 62, 22))
    assert r.action == "Downsize"
    assert r.recommended_type == "c6i.2xlarge"     # xlarge would put memory at 88%
    assert r.projected_cpu_p95 == 18.0


def test_without_memory_data_only_one_step_down():
    r = rightsizing.recommend(Usage("i-3", "dev", "m6i.4xlarge", 4, 30, None))
    assert r.recommended_type == "m6i.2xlarge"
    assert r.notes


def test_hot_instance_is_upsized_and_keep_when_right():
    assert rightsizing.recommend(Usage("i-4", "api", "c6i.xlarge", 91, 99, 50)).recommended_type == "c6i.2xlarge"
    keep = rightsizing.recommend(Usage("i-5", "db", "r6i.2xlarge", 46, 77, 81))
    assert keep.action == "Keep" and keep.monthly_savings == 0


def test_burstable_instances_project_memory_and_baseline_not_cpu():
    r = rightsizing.recommend(Usage("i-6", "web", "t3.large", 8, 12, 5))
    assert r.action == "Downsize" and r.recommended_type == "t3.micro"    # nano's 5% baseline is below 8%
    assert r.projected_cpu_p95 == 8.0                                     # same 2 vCPUs
    burner = rightsizing.recommend(Usage("i-7", "ci", "t3.small", 35, 40, 30))
    assert burner.action == "Burst-bound" and burner.recommended_type == "m7i.large"
    assert pricing.vcpus("t3.medium") == pricing.vcpus("t3.large") == 2
    assert pricing.memory_gib("r6i.xlarge") == 32


def test_schedules():
    assert scheduling.OFFICE_HOURS.hours_per_week == 60
    s = scheduling.parse_schedule("night:22-06:Mon-Sun")
    assert s.hours_per_week == 56
    assert scheduling.parse_schedule("ops:08-18:Mon,Wed,Fri").hours_per_week == 30
    with pytest.raises(ValueError):
        scheduling.parse_schedule("bad:08-18:Funday")
    saving = scheduling.schedule_saving("i", "n", "m6i.xlarge", scheduling.OFFICE_HOURS)
    assert saving.monthly_savings == pytest.approx(saving.always_on_monthly * (1 - 60 / 168), abs=0.02)


def test_spot_quote():
    q = scheduling.spot_quote("m6i.large", 0.0384, "test")
    assert q.discount_pct == 60.0
    assert scheduling.spot_quote("unknown.large", 0.01, "test") is None


def test_showback_groups_by_tag_and_measures_untagged():
    lines = [showback.CostLine("2026-09", "web", "EC2", 70), showback.CostLine("2026-09", "", "S3", 30),
             showback.CostLine("2026-10", "web", "EC2", 80), showback.CostLine("2026-10", "data", "EC2", 20)]
    sb = showback.build(lines)
    assert sb.months == ["2026-09", "2026-10"]
    assert list(sb.by_owner)[-1] == showback.UNTAGGED
    assert sb.untagged_pct == 15.0
    assert sb.top_untagged_services == [("S3", 30)]
    assert sb.totals == {"2026-09": 100, "2026-10": 100}


def test_eks_pricing_uses_spot_prices_when_given():
    nodes = [eks.Node("a", "m6i.large", "on-demand", "node-group", 2, 1), eks.Node("b", "m6i.large", "spot", "karpenter", 2, 1)]
    c = eks.price_nodes(nodes, {"m6i.large": 0.03})
    assert c.hourly == pytest.approx(0.096 + 0.03)
    assert c.spot_nodes == 1 and c.requested_cpu_pct == 50.0
    before, after = eks.price_nodes(eks.DEMO_BEFORE), eks.price_nodes(eks.DEMO_AFTER)
    assert after.monthly < before.monthly
    assert sum(n.cpu_requested for n in eks.DEMO_BEFORE) == pytest.approx(sum(n.cpu_requested for n in eks.DEMO_AFTER))


def test_report_escapes_values():
    html = report.render({"rightsizing": [rightsizing.recommend(Usage("i-9", "<script>x</script>", "m6i.large", 50, 60, 50)).to_dict()]})
    assert "<script>x" not in html and "&lt;script&gt;x" in html


def test_demo_report_end_to_end(tmp_path):
    out, js = tmp_path / "r.html", tmp_path / "r.json"
    subprocess.run([sys.executable, "-m", "costlab", "report", "--demo", "--html", str(out), "--json", str(js)], cwd=ROOT, check=True, capture_output=True)
    data = json.loads(js.read_text())
    assert {"rightsizing", "schedule", "spot", "showback", "eks"} <= set(data)
    assert len(data["rightsizing"]) == len(demo.USAGE)
    assert "Showback by CostCenter" in out.read_text()


def test_scheduler_lambda_only_touches_tagged_standalone_instances(monkeypatch):
    import importlib.util
    import types

    calls = {}

    class FakePaginator:
        def paginate(self, Filters):
            calls["filters"] = Filters
            yield {"Reservations": [{"Instances": [
                {"InstanceId": "i-dev", "Tags": [{"Key": "Schedule", "Value": "office-hours"}]},
                {"InstanceId": "i-spot", "InstanceLifecycle": "spot", "Tags": []},
                {"InstanceId": "i-asg", "Tags": [{"Key": "aws:autoscaling:groupName", "Value": "web"}]},
            ]}]}

    class FakeEC2:
        def get_paginator(self, name):
            return FakePaginator()

        def stop_instances(self, InstanceIds):
            calls["stopped"] = InstanceIds

        def start_instances(self, InstanceIds):
            calls["started"] = InstanceIds

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda name: FakeEC2()))
    spec = importlib.util.spec_from_file_location("scheduler", ROOT / "labs/02-spot-and-scheduling/lambda/scheduler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.handler({"action": "stop"}, None)
    assert out["instances"] == ["i-dev"] and calls["stopped"] == ["i-dev"]
    assert {"Name": "instance-state-name", "Values": ["running"]} in calls["filters"]
    with pytest.raises(ValueError):
        mod.handler({"action": "reboot"}, None)


def test_karpenter_manifests_are_valid_v1_yaml():
    yaml = pytest.importorskip("yaml")
    lab = ROOT / "labs/04-eks-karpenter/manifests"
    text = (lab / "karpenter.yaml.tftpl").read_text()
    for key, value in {"cluster_name": "lab", "node_role": "lab-node", "capacity_types": '["spot","on-demand"]', "cost_center": "platform"}.items():
        text = text.replace("${" + key + "}", value)
    assert "${" not in text
    docs = list(yaml.safe_load_all(text))
    kinds = {(d["apiVersion"], d["kind"]) for d in docs}
    assert kinds == {("karpenter.k8s.aws/v1", "EC2NodeClass"), ("karpenter.sh/v1", "NodePool")}
    pool = next(d for d in docs if d["kind"] == "NodePool")
    assert pool["spec"]["disruption"]["consolidationPolicy"] == "WhenEmptyOrUnderutilized"
    cap = next(r for r in pool["spec"]["template"]["spec"]["requirements"] if r["key"] == "karpenter.sh/capacity-type")
    assert cap["values"] == ["spot", "on-demand"]
    inflate = yaml.safe_load((lab / "inflate.yaml").read_text())
    assert inflate["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] == "1"
