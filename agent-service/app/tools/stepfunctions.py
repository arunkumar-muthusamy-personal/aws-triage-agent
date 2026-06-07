from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_state_machines() -> dict:
    """List all Step Functions state machines in the account/region.

    Returns a dict with 'state_machines' list of {stateMachineArn, name, type, creationDate}.
    """
    try:
        client = boto3.client("stepfunctions", region_name=settings.aws_region)
        machines = []
        paginator = client.get_paginator("list_state_machines")
        for page in paginator.paginate():
            for sm in page.get("stateMachines", []):
                machines.append(
                    {
                        "stateMachineArn": sm.get("stateMachineArn"),
                        "name": sm.get("name"),
                        "type": sm.get("type"),
                        "creationDate": sm.get("creationDate", "").isoformat()
                        if sm.get("creationDate")
                        else None,
                    }
                )
        return {"state_machines": machines}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_state_machine(state_machine_arn: str) -> dict:
    """Describe a Step Functions state machine.

    Args:
        state_machine_arn: The state machine ARN.

    Returns a dict with state machine details including definition and logging config.
    """
    try:
        client = boto3.client("stepfunctions", region_name=settings.aws_region)
        response = client.describe_state_machine(stateMachineArn=state_machine_arn)
        return {
            "stateMachineArn": response.get("stateMachineArn"),
            "name": response.get("name"),
            "status": response.get("status"),
            "type": response.get("type"),
            "roleArn": response.get("roleArn"),
            "definition": response.get("definition"),
            "loggingConfiguration": response.get("loggingConfiguration", {}),
            "tracingConfiguration": response.get("tracingConfiguration", {}),
            "creationDate": response.get("creationDate", "").isoformat()
            if response.get("creationDate")
            else None,
        }
    except ClientError as e:
        return {"error": str(e)}


@tool
def list_executions(
    state_machine_arn: str,
    status_filter: Optional[str] = None,
    max_results: int = 50,
) -> dict:
    """List executions of a Step Functions state machine.

    Args:
        state_machine_arn: The state machine ARN.
        status_filter: Optional status filter: 'RUNNING', 'SUCCEEDED', 'FAILED',
                       'TIMED_OUT', or 'ABORTED'.
        max_results: Maximum number of executions to return (default 50).

    Returns a dict with 'executions' list.
    """
    try:
        client = boto3.client("stepfunctions", region_name=settings.aws_region)
        kwargs: dict = {"stateMachineArn": state_machine_arn, "maxResults": max_results}
        if status_filter:
            kwargs["statusFilter"] = status_filter

        executions = []
        paginator = client.get_paginator("list_executions")
        for page in paginator.paginate(**kwargs):
            for exe in page.get("executions", []):
                executions.append(
                    {
                        "executionArn": exe.get("executionArn"),
                        "name": exe.get("name"),
                        "status": exe.get("status"),
                        "startDate": exe.get("startDate", "").isoformat()
                        if exe.get("startDate")
                        else None,
                        "stopDate": exe.get("stopDate", "").isoformat()
                        if exe.get("stopDate")
                        else None,
                    }
                )
            if len(executions) >= max_results:
                break

        return {"state_machine_arn": state_machine_arn, "executions": executions[:max_results]}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_execution_history(
    execution_arn: str,
    max_results: int = 100,
    reverse_order: bool = True,
) -> dict:
    """Get the event history for a Step Functions execution.

    Args:
        execution_arn: The execution ARN.
        max_results: Maximum number of events to return (default 100).
        reverse_order: If True, returns events in reverse chronological order (default True).

    Returns a dict with 'events' list including type, timestamp, and details.
    """
    try:
        client = boto3.client("stepfunctions", region_name=settings.aws_region)
        events = []
        paginator = client.get_paginator("get_execution_history")
        for page in paginator.paginate(
            executionArn=execution_arn,
            reverseOrder=reverse_order,
            maxResults=max_results,
        ):
            for event in page.get("events", []):
                events.append(
                    {
                        "id": event.get("id"),
                        "type": event.get("type"),
                        "timestamp": event.get("timestamp", "").isoformat()
                        if event.get("timestamp")
                        else None,
                        "previousEventId": event.get("previousEventId"),
                        # Include whichever detail key is present
                        **{
                            k: v
                            for k, v in event.items()
                            if k not in ("id", "type", "timestamp", "previousEventId")
                        },
                    }
                )
            if len(events) >= max_results:
                break

        return {"execution_arn": execution_arn, "events": events[:max_results]}
    except ClientError as e:
        return {"error": str(e)}
