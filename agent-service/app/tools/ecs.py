from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_ecs_clusters() -> dict:
    """List all ECS cluster ARNs in the account.

    Returns a dict with 'cluster_arns' list.
    """
    try:
        client = boto3.client("ecs", region_name=settings.aws_region)
        arns = []
        paginator = client.get_paginator("list_clusters")
        for page in paginator.paginate():
            arns.extend(page.get("clusterArns", []))
        return {"cluster_arns": arns}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_ecs_services(cluster: str, services: list[str]) -> dict:
    """Describe one or more ECS services in a cluster.

    Args:
        cluster: The ECS cluster name or ARN.
        services: List of service names or ARNs (max 10 per call).

    Returns a dict with 'services' list of service details.
    """
    try:
        client = boto3.client("ecs", region_name=settings.aws_region)
        response = client.describe_services(cluster=cluster, services=services)
        return {
            "services": response.get("services", []),
            "failures": response.get("failures", []),
        }
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_ecs_tasks(
    cluster: str,
    family: Optional[str] = None,
    desired_status: Optional[str] = None,
    service_name: Optional[str] = None,
) -> dict:
    """List and describe ECS tasks in a cluster, with optional filters.

    Args:
        cluster: The ECS cluster name or ARN.
        family: Optional task definition family to filter by.
        desired_status: Optional status filter: 'RUNNING', 'PENDING', or 'STOPPED'.
        service_name: Optional service name to filter tasks.

    Returns a dict with 'tasks' list of task details.
    """
    try:
        client = boto3.client("ecs", region_name=settings.aws_region)
        list_kwargs: dict = {"cluster": cluster}
        if family:
            list_kwargs["family"] = family
        if desired_status:
            list_kwargs["desiredStatus"] = desired_status
        if service_name:
            list_kwargs["serviceName"] = service_name

        task_arns = []
        paginator = client.get_paginator("list_tasks")
        for page in paginator.paginate(**list_kwargs):
            task_arns.extend(page.get("taskArns", []))

        if not task_arns:
            return {"tasks": []}

        # Describe in batches of 100
        tasks = []
        for i in range(0, len(task_arns), 100):
            batch = task_arns[i : i + 100]
            response = client.describe_tasks(cluster=cluster, tasks=batch)
            tasks.extend(response.get("tasks", []))

        return {"tasks": tasks}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_task_stopped_reason(cluster: str, task_id: str) -> dict:
    """Get the stopped reason and container exit codes for a specific ECS task.

    Args:
        cluster: The ECS cluster name or ARN.
        task_id: The ECS task ID or ARN.

    Returns a dict with 'stoppedReason', 'stopCode', and 'containers' exit info.
    """
    try:
        client = boto3.client("ecs", region_name=settings.aws_region)
        response = client.describe_tasks(cluster=cluster, tasks=[task_id])
        tasks = response.get("tasks", [])
        if not tasks:
            return {"error": f"Task {task_id} not found"}

        task = tasks[0]
        containers = [
            {
                "name": c.get("name"),
                "exitCode": c.get("exitCode"),
                "reason": c.get("reason"),
                "lastStatus": c.get("lastStatus"),
            }
            for c in task.get("containers", [])
        ]
        return {
            "stoppedReason": task.get("stoppedReason"),
            "stopCode": task.get("stopCode"),
            "lastStatus": task.get("lastStatus"),
            "containers": containers,
            "startedAt": task.get("startedAt", ""),
            "stoppedAt": task.get("stoppedAt", ""),
        }
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_ecs_container_instances(cluster: str, container_instances: list[str]) -> dict:
    """Describe ECS container instances in a cluster.

    Args:
        cluster: The ECS cluster name or ARN.
        container_instances: List of container instance IDs or ARNs.

    Returns a dict with 'containerInstances' list of instance details.
    """
    try:
        client = boto3.client("ecs", region_name=settings.aws_region)
        response = client.describe_container_instances(
            cluster=cluster, containerInstances=container_instances
        )
        return {
            "containerInstances": response.get("containerInstances", []),
            "failures": response.get("failures", []),
        }
    except ClientError as e:
        return {"error": str(e)}
