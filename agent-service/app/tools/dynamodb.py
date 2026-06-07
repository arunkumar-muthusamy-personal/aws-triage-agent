from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def describe_dynamodb_table(table_name: str) -> dict:
    """Describe a DynamoDB table including its configuration and status.

    Args:
        table_name: The DynamoDB table name.

    Returns a dict with table description details.
    """
    try:
        client = boto3.client("dynamodb", region_name=settings.aws_region)
        response = client.describe_table(TableName=table_name)
        return {"table": response.get("Table", {})}
    except ClientError as e:
        return {"error": str(e)}


@tool
def list_dynamodb_tables() -> dict:
    """List all DynamoDB table names in the account/region.

    Returns a dict with 'table_names' list.
    """
    try:
        client = boto3.client("dynamodb", region_name=settings.aws_region)
        table_names = []
        paginator = client.get_paginator("list_tables")
        for page in paginator.paginate():
            table_names.extend(page.get("TableNames", []))
        return {"table_names": table_names}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_dynamodb_metrics(
    table_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    period: int = 300,
) -> dict:
    """Retrieve CloudWatch metrics for a DynamoDB table.

    Fetches: ConsumedReadCapacityUnits, ConsumedWriteCapacityUnits,
    ThrottledRequests, SystemErrors, SuccessfulRequestLatency.

    Args:
        table_name: The DynamoDB table name.
        start_time: ISO 8601 start time (defaults to 1 hour ago).
        end_time: ISO 8601 end time (defaults to now).
        period: Period in seconds (default 300).

    Returns a dict with per-metric datapoints.
    """
    try:
        cw_client = boto3.client("cloudwatch", region_name=settings.aws_region)
        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(start_time) if start_time else now - timedelta(hours=1)
        end = datetime.fromisoformat(end_time) if end_time else now

        metrics = [
            ("ConsumedReadCapacityUnits", ["Sum"]),
            ("ConsumedWriteCapacityUnits", ["Sum"]),
            ("ThrottledRequests", ["Sum"]),
            ("SystemErrors", ["Sum"]),
            ("SuccessfulRequestLatency", ["Average", "p99"]),
        ]

        result: dict = {}
        for metric_name, statistics in metrics:
            response = cw_client.get_metric_statistics(
                Namespace="AWS/DynamoDB",
                MetricName=metric_name,
                Dimensions=[{"Name": "TableName", "Value": table_name}],
                StartTime=start,
                EndTime=end,
                Period=period,
                Statistics=[s for s in statistics if s != "p99"],
                ExtendedStatistics=["p99"] if "p99" in statistics else [],
            )
            result[metric_name] = sorted(
                [
                    {
                        "timestamp": dp["Timestamp"].isoformat(),
                        **{k: v for k, v in dp.items() if k not in ("Timestamp", "Unit")},
                    }
                    for dp in response.get("Datapoints", [])
                ],
                key=lambda x: x["timestamp"],
            )

        return {"table_name": table_name, "metrics": result}
    except ClientError as e:
        return {"error": str(e)}
