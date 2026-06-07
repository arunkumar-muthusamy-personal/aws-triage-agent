from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings
from app.tools.time_utils import parse_aws_datetime


@tool
def get_metric_statistics(
    namespace: str,
    metric_name: str,
    dimensions: list[dict],
    start_time: str,
    end_time: str,
    period: int,
    statistics: list[str],
) -> dict:
    """Retrieve CloudWatch metric statistics for a given metric.

    Args:
        namespace: CloudWatch metric namespace (e.g. 'AWS/EC2').
        metric_name: The metric name (e.g. 'CPUUtilization').
        dimensions: List of {Name, Value} dicts specifying metric dimensions.
        start_time: ISO 8601 start time string.
        end_time: ISO 8601 end time string.
        period: Period in seconds for each data point.
        statistics: List of statistics to retrieve (e.g. ['Average', 'Maximum']).

    Returns a dict with 'datapoints' sorted by timestamp.
    """
    try:
        client = boto3.client("cloudwatch", region_name=settings.aws_region)
        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=parse_aws_datetime(start_time, datetime.now(timezone.utc)),
            EndTime=parse_aws_datetime(end_time, datetime.now(timezone.utc)),
            Period=period,
            Statistics=statistics,
        )
        datapoints = sorted(
            [
                {
                    "timestamp": dp["Timestamp"].isoformat(),
                    **{stat: dp.get(stat) for stat in statistics if stat in dp},
                    "unit": dp.get("Unit"),
                }
                for dp in response.get("Datapoints", [])
            ],
            key=lambda x: x["timestamp"],
        )
        return {"datapoints": datapoints, "metric_name": metric_name}
    except ClientError as e:
        return {"error": str(e)}


@tool
def list_metrics(
    namespace: Optional[str] = None,
    metric_name: Optional[str] = None,
    dimensions: Optional[list[dict]] = None,
) -> dict:
    """List available CloudWatch metrics, optionally filtered by namespace and metric name.

    Args:
        namespace: Optional CloudWatch namespace filter.
        metric_name: Optional metric name filter.
        dimensions: Optional list of {Name, Value} dimension filters.

    Returns a dict with 'metrics' list of {Namespace, MetricName, Dimensions}.
    """
    try:
        client = boto3.client("cloudwatch", region_name=settings.aws_region)
        kwargs: dict = {}
        if namespace:
            kwargs["Namespace"] = namespace
        if metric_name:
            kwargs["MetricName"] = metric_name
        if dimensions:
            kwargs["Dimensions"] = dimensions

        metrics = []
        paginator = client.get_paginator("list_metrics")
        for page in paginator.paginate(**kwargs):
            for m in page.get("Metrics", []):
                metrics.append(
                    {
                        "Namespace": m["Namespace"],
                        "MetricName": m["MetricName"],
                        "Dimensions": m.get("Dimensions", []),
                    }
                )

        return {"metrics": metrics}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_alarms(
    alarm_names: Optional[list[str]] = None,
    state_value: Optional[str] = None,
    alarm_name_prefix: Optional[str] = None,
) -> dict:
    """Describe CloudWatch alarms, optionally filtered by name or state.

    Args:
        alarm_names: Optional list of alarm names to describe.
        state_value: Optional state filter: 'OK', 'ALARM', or 'INSUFFICIENT_DATA'.
        alarm_name_prefix: Optional prefix to filter alarm names.

    Returns a dict with 'alarms' list including StateValue, StateReason,
    Threshold, ComparisonOperator, and MetricName.
    """
    try:
        client = boto3.client("cloudwatch", region_name=settings.aws_region)
        kwargs: dict = {}
        if alarm_names:
            kwargs["AlarmNames"] = alarm_names
        if state_value:
            kwargs["StateValue"] = state_value
        if alarm_name_prefix:
            kwargs["AlarmNamePrefix"] = alarm_name_prefix

        alarms = []
        paginator = client.get_paginator("describe_alarms")
        for page in paginator.paginate(**kwargs):
            for alarm in page.get("MetricAlarms", []):
                alarms.append(
                    {
                        "AlarmName": alarm.get("AlarmName"),
                        "AlarmDescription": alarm.get("AlarmDescription"),
                        "StateValue": alarm.get("StateValue"),
                        "StateReason": alarm.get("StateReason"),
                        "Threshold": alarm.get("Threshold"),
                        "ComparisonOperator": alarm.get("ComparisonOperator"),
                        "MetricName": alarm.get("MetricName"),
                        "Namespace": alarm.get("Namespace"),
                        "Dimensions": alarm.get("Dimensions", []),
                        "Period": alarm.get("Period"),
                        "EvaluationPeriods": alarm.get("EvaluationPeriods"),
                        "StateUpdatedTimestamp": alarm.get("StateUpdatedTimestamp", "").isoformat()
                        if alarm.get("StateUpdatedTimestamp")
                        else None,
                    }
                )

        return {"alarms": alarms}
    except ClientError as e:
        return {"error": str(e)}
