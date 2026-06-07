import time
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def query_cloudwatch_logs(
    log_group_name: str,
    query_string: str,
    start_time: str,
    end_time: str,
    limit: int = 1000,
) -> dict:
    """Run a CloudWatch Logs Insights query and return results.

    Args:
        log_group_name: The log group to query.
        query_string: CloudWatch Logs Insights query string.
        start_time: ISO 8601 start time string.
        end_time: ISO 8601 end time string.
        limit: Maximum number of log records to return (default 1000).

    Returns a dict with 'results' (list of field dicts) and 'statistics'.
    Polls every 1 second with a 60 second timeout.
    """
    try:
        client = boto3.client("logs", region_name=settings.aws_region)
        start_ts = int(datetime.fromisoformat(start_time).timestamp())
        end_ts = int(datetime.fromisoformat(end_time).timestamp())

        response = client.start_query(
            logGroupName=log_group_name,
            startTime=start_ts,
            endTime=end_ts,
            queryString=query_string,
            limit=min(limit, settings.log_query_max_records),
        )
        query_id = response["queryId"]

        deadline = time.time() + 60
        while time.time() < deadline:
            result = client.get_query_results(queryId=query_id)
            status = result["status"]
            if status in ("Complete", "Failed", "Cancelled", "Timeout"):
                return {
                    "status": status,
                    "results": [
                        {field["field"]: field["value"] for field in row}
                        for row in result.get("results", [])
                    ],
                    "statistics": result.get("statistics", {}),
                }
            time.sleep(1)

        # Timeout — cancel and return what we have
        try:
            client.stop_query(queryId=query_id)
        except ClientError:
            pass
        return {"status": "Timeout", "results": [], "statistics": {}}
    except ClientError as e:
        return {"error": str(e)}


@tool
def list_log_groups(prefix: Optional[str] = None) -> dict:
    """List CloudWatch log groups, optionally filtered by a name prefix.

    Args:
        prefix: Optional log group name prefix to filter results.

    Returns a dict with 'log_groups' list of log group names.
    """
    try:
        client = boto3.client("logs", region_name=settings.aws_region)
        kwargs: dict = {}
        if prefix:
            kwargs["logGroupNamePrefix"] = prefix

        log_groups = []
        paginator = client.get_paginator("describe_log_groups")
        for page in paginator.paginate(**kwargs):
            for lg in page.get("logGroups", []):
                log_groups.append(lg["logGroupName"])

        return {"log_groups": log_groups}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_log_events(
    log_group_name: str,
    log_stream_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
) -> dict:
    """Retrieve log events from a specific CloudWatch log stream.

    Args:
        log_group_name: The log group name.
        log_stream_name: The log stream name.
        start_time: Optional ISO 8601 start time string.
        end_time: Optional ISO 8601 end time string.
        limit: Maximum number of events to return (default 100).

    Returns a dict with 'events' list of {timestamp, message}.
    """
    try:
        client = boto3.client("logs", region_name=settings.aws_region)
        kwargs: dict = {
            "logGroupName": log_group_name,
            "logStreamName": log_stream_name,
            "limit": limit,
            "startFromHead": True,
        }
        if start_time:
            kwargs["startTime"] = int(datetime.fromisoformat(start_time).timestamp() * 1000)
        if end_time:
            kwargs["endTime"] = int(datetime.fromisoformat(end_time).timestamp() * 1000)

        response = client.get_log_events(**kwargs)
        events = [
            {
                "timestamp": datetime.utcfromtimestamp(e["timestamp"] / 1000).isoformat(),
                "message": e["message"],
            }
            for e in response.get("events", [])
        ]
        return {"events": events}
    except ClientError as e:
        return {"error": str(e)}


@tool
def filter_log_events(
    log_group_name: str,
    filter_pattern: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    log_stream_names: Optional[list[str]] = None,
    limit: int = 100,
) -> dict:
    """Filter log events across streams in a CloudWatch log group by a pattern.

    Args:
        log_group_name: The log group to search.
        filter_pattern: CloudWatch filter pattern string.
        start_time: Optional ISO 8601 start time string.
        end_time: Optional ISO 8601 end time string.
        log_stream_names: Optional list of log stream names to restrict search.
        limit: Maximum number of events to return (default 100).

    Returns a dict with 'events' list of {timestamp, message, logStreamName}.
    """
    try:
        client = boto3.client("logs", region_name=settings.aws_region)
        kwargs: dict = {
            "logGroupName": log_group_name,
            "filterPattern": filter_pattern,
            "limit": limit,
        }
        if start_time:
            kwargs["startTime"] = int(datetime.fromisoformat(start_time).timestamp() * 1000)
        if end_time:
            kwargs["endTime"] = int(datetime.fromisoformat(end_time).timestamp() * 1000)
        if log_stream_names:
            kwargs["logStreamNames"] = log_stream_names

        response = client.filter_log_events(**kwargs)
        events = [
            {
                "timestamp": datetime.utcfromtimestamp(e["timestamp"] / 1000).isoformat(),
                "message": e["message"],
                "logStreamName": e.get("logStreamName", ""),
            }
            for e in response.get("events", [])
        ]
        return {"events": events}
    except ClientError as e:
        return {"error": str(e)}
