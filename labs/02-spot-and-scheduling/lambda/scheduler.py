"""Stops or starts every EC2 instance tagged with the schedule.

Invoked by EventBridge Scheduler with {"action": "stop"} or {"action": "start"}. The IAM policy
only allows stop/start on instances that carry the tag, so a bug here cannot touch anything else.
"""
import os

import boto3

ec2 = boto3.client("ec2")


def _instances(tag_key: str, tag_value: str, state: str) -> list[str]:
    ids = []
    for page in ec2.get_paginator("describe_instances").paginate(Filters=[
        {"Name": f"tag:{tag_key}", "Values": [tag_value]},
        {"Name": "instance-state-name", "Values": [state]},
    ]):
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                # Spot instances and Auto Scaling members are handled by their own mechanisms.
                if instance.get("InstanceLifecycle") == "spot":
                    continue
                if any(t["Key"] == "aws:autoscaling:groupName" for t in instance.get("Tags", [])):
                    continue
                ids.append(instance["InstanceId"])
    return ids


def handler(event, context):
    action = (event or {}).get("action")
    if action not in ("stop", "start"):
        raise ValueError('expected {"action": "stop"} or {"action": "start"}')
    tag_key = os.environ.get("TAG_KEY", "Schedule")
    tag_value = (event or {}).get("schedule") or os.environ.get("TAG_VALUE", "office-hours")
    ids = _instances(tag_key, tag_value, "running" if action == "stop" else "stopped")
    if ids:
        if action == "stop":
            ec2.stop_instances(InstanceIds=ids)
        else:
            ec2.start_instances(InstanceIds=ids)
    print(f"{action}: {len(ids)} instance(s) tagged {tag_key}={tag_value}: {ids}")
    return {"action": action, "instances": ids}
