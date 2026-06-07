from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def describe_instances(
    instance_ids: Optional[list[str]] = None,
    filters: Optional[list[dict]] = None,
) -> dict:
    """Describe EC2 instances, optionally filtered by instance IDs or filters.

    Args:
        instance_ids: Optional list of instance IDs to describe.
        filters: Optional list of {Name, Values} filter dicts.

    Returns a dict with 'reservations' containing instance details.
    """
    try:
        client = boto3.client("ec2", region_name=settings.aws_region)
        kwargs: dict = {}
        if instance_ids:
            kwargs["InstanceIds"] = instance_ids
        if filters:
            kwargs["Filters"] = filters

        instances = []
        paginator = client.get_paginator("describe_instances")
        for page in paginator.paginate(**kwargs):
            instances.extend(page.get("Reservations", []))

        return {"reservations": instances}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_security_groups(
    group_ids: Optional[list[str]] = None,
    filters: Optional[list[dict]] = None,
) -> dict:
    """Describe EC2 security groups, optionally filtered by IDs or filters.

    Args:
        group_ids: Optional list of security group IDs.
        filters: Optional list of {Name, Values} filter dicts.

    Returns a dict with 'security_groups' list.
    """
    try:
        client = boto3.client("ec2", region_name=settings.aws_region)
        kwargs: dict = {}
        if group_ids:
            kwargs["GroupIds"] = group_ids
        if filters:
            kwargs["Filters"] = filters

        sgs = []
        paginator = client.get_paginator("describe_security_groups")
        for page in paginator.paginate(**kwargs):
            sgs.extend(page.get("SecurityGroups", []))

        return {"security_groups": sgs}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_vpcs(
    vpc_ids: Optional[list[str]] = None,
    filters: Optional[list[dict]] = None,
) -> dict:
    """Describe VPCs, optionally filtered by VPC IDs or filters.

    Args:
        vpc_ids: Optional list of VPC IDs.
        filters: Optional list of {Name, Values} filter dicts.

    Returns a dict with 'vpcs' list.
    """
    try:
        client = boto3.client("ec2", region_name=settings.aws_region)
        kwargs: dict = {}
        if vpc_ids:
            kwargs["VpcIds"] = vpc_ids
        if filters:
            kwargs["Filters"] = filters

        vpcs = []
        paginator = client.get_paginator("describe_vpcs")
        for page in paginator.paginate(**kwargs):
            vpcs.extend(page.get("Vpcs", []))

        return {"vpcs": vpcs}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_subnets(
    subnet_ids: Optional[list[str]] = None,
    filters: Optional[list[dict]] = None,
) -> dict:
    """Describe subnets, optionally filtered by subnet IDs or filters.

    Args:
        subnet_ids: Optional list of subnet IDs.
        filters: Optional list of {Name, Values} filter dicts. Example:
                 [{"Name": "vpc-id", "Values": ["vpc-xxx"]}]

    Returns a dict with 'subnets' list.
    """
    try:
        client = boto3.client("ec2", region_name=settings.aws_region)
        kwargs: dict = {}
        if subnet_ids:
            kwargs["SubnetIds"] = subnet_ids
        if filters:
            kwargs["Filters"] = filters

        subnets = []
        paginator = client.get_paginator("describe_subnets")
        for page in paginator.paginate(**kwargs):
            subnets.extend(page.get("Subnets", []))

        return {"subnets": subnets}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_autoscaling_groups(
    group_names: Optional[list[str]] = None,
) -> dict:
    """Describe Auto Scaling groups and their recent scaling activities.

    Args:
        group_names: Optional list of Auto Scaling group names to describe.

    Returns a dict with 'autoscaling_groups' list including recent scaling activities.
    """
    try:
        asg_client = boto3.client("autoscaling", region_name=settings.aws_region)
        kwargs: dict = {}
        if group_names:
            kwargs["AutoScalingGroupNames"] = group_names

        groups = []
        paginator = asg_client.get_paginator("describe_auto_scaling_groups")
        for page in paginator.paginate(**kwargs):
            groups.extend(page.get("AutoScalingGroups", []))

        result = []
        for group in groups:
            group_name = group["AutoScalingGroupName"]
            # Get recent scaling activities
            activities_resp = asg_client.describe_scaling_activities(
                AutoScalingGroupName=group_name, MaxRecords=10
            )
            activities = [
                {
                    "ActivityId": a.get("ActivityId"),
                    "Description": a.get("Description"),
                    "StatusCode": a.get("StatusCode"),
                    "StartTime": a.get("StartTime", "").isoformat() if a.get("StartTime") else None,
                    "EndTime": a.get("EndTime", "").isoformat() if a.get("EndTime") else None,
                    "StatusMessage": a.get("StatusMessage"),
                }
                for a in activities_resp.get("Activities", [])
            ]
            result.append({**group, "RecentScalingActivities": activities})

        return {"autoscaling_groups": result}
    except ClientError as e:
        return {"error": str(e)}
