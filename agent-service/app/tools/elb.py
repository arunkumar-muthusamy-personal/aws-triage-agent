from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def describe_load_balancers(
    load_balancer_arns: Optional[list[str]] = None,
    names: Optional[list[str]] = None,
) -> dict:
    """Describe Application, Network, or Gateway Load Balancers (ELBv2).

    Args:
        load_balancer_arns: Optional list of load balancer ARNs.
        names: Optional list of load balancer names.

    Returns a dict with 'load_balancers' list.
    """
    try:
        client = boto3.client("elbv2", region_name=settings.aws_region)
        kwargs: dict = {}
        if load_balancer_arns:
            kwargs["LoadBalancerArns"] = load_balancer_arns
        if names:
            kwargs["Names"] = names

        lbs = []
        paginator = client.get_paginator("describe_load_balancers")
        for page in paginator.paginate(**kwargs):
            lbs.extend(page.get("LoadBalancers", []))

        return {"load_balancers": lbs}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_listeners(load_balancer_arn: str) -> dict:
    """Describe listeners attached to an ELBv2 load balancer.

    Args:
        load_balancer_arn: The ARN of the load balancer.

    Returns a dict with 'listeners' list.
    """
    try:
        client = boto3.client("elbv2", region_name=settings.aws_region)
        listeners = []
        paginator = client.get_paginator("describe_listeners")
        for page in paginator.paginate(LoadBalancerArn=load_balancer_arn):
            listeners.extend(page.get("Listeners", []))
        return {"load_balancer_arn": load_balancer_arn, "listeners": listeners}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_target_groups(
    load_balancer_arn: Optional[str] = None,
    target_group_arns: Optional[list[str]] = None,
) -> dict:
    """Describe ELBv2 target groups, optionally filtered by load balancer or ARNs.

    Args:
        load_balancer_arn: Optional load balancer ARN to filter target groups.
        target_group_arns: Optional list of target group ARNs.

    Returns a dict with 'target_groups' list.
    """
    try:
        client = boto3.client("elbv2", region_name=settings.aws_region)
        kwargs: dict = {}
        if load_balancer_arn:
            kwargs["LoadBalancerArn"] = load_balancer_arn
        if target_group_arns:
            kwargs["TargetGroupArns"] = target_group_arns

        tgs = []
        paginator = client.get_paginator("describe_target_groups")
        for page in paginator.paginate(**kwargs):
            tgs.extend(page.get("TargetGroups", []))

        return {"target_groups": tgs}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_target_health(target_group_arn: str) -> dict:
    """Describe the health of targets registered with an ELBv2 target group.

    Args:
        target_group_arn: The ARN of the target group.

    Returns a dict with 'target_health_descriptions' list including HealthState and reason.
    """
    try:
        client = boto3.client("elbv2", region_name=settings.aws_region)
        response = client.describe_target_health(TargetGroupArn=target_group_arn)
        return {
            "target_group_arn": target_group_arn,
            "target_health_descriptions": response.get("TargetHealthDescriptions", []),
        }
    except ClientError as e:
        return {"error": str(e)}
