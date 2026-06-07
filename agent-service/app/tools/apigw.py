from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_rest_apis() -> dict:
    """List all API Gateway REST APIs.

    Returns a dict with 'apis' list of {id, name, description, createdDate}.
    """
    try:
        client = boto3.client("apigateway", region_name=settings.aws_region)
        apis = []
        paginator = client.get_paginator("get_rest_apis")
        for page in paginator.paginate():
            for api in page.get("items", []):
                apis.append(
                    {
                        "id": api.get("id"),
                        "name": api.get("name"),
                        "description": api.get("description"),
                        "createdDate": api.get("createdDate", "").isoformat()
                        if api.get("createdDate")
                        else None,
                    }
                )
        return {"apis": apis}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_stages(rest_api_id: str) -> dict:
    """Get all deployment stages for an API Gateway REST API.

    Args:
        rest_api_id: The REST API ID.

    Returns a dict with 'stages' list including stage name, deployment ID,
    and method settings.
    """
    try:
        client = boto3.client("apigateway", region_name=settings.aws_region)
        response = client.get_stages(restApiId=rest_api_id)
        return {"rest_api_id": rest_api_id, "stages": response.get("item", [])}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_api_gateway_metrics(
    api_name: str,
    stage: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    period: int = 300,
) -> dict:
    """Retrieve CloudWatch metrics for an API Gateway stage.

    Fetches: Count, 4XXError, 5XXError, Latency, IntegrationLatency.

    Args:
        api_name: The API name (used as dimension value).
        stage: The stage name (e.g. 'prod').
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

        metrics_config = [
            ("Count", ["Sum"]),
            ("4XXError", ["Sum"]),
            ("5XXError", ["Sum"]),
            ("Latency", ["Average", "p99"]),
            ("IntegrationLatency", ["Average", "p99"]),
        ]

        dimensions = [
            {"Name": "ApiName", "Value": api_name},
            {"Name": "Stage", "Value": stage},
        ]

        result: dict = {}
        for metric_name, statistics in metrics_config:
            std_stats = [s for s in statistics if s != "p99"]
            ext_stats = ["p99"] if "p99" in statistics else []
            kwargs = {
                "Namespace": "AWS/ApiGateway",
                "MetricName": metric_name,
                "Dimensions": dimensions,
                "StartTime": start,
                "EndTime": end,
                "Period": period,
            }
            if std_stats:
                kwargs["Statistics"] = std_stats
            if ext_stats:
                kwargs["ExtendedStatistics"] = ext_stats
            response = cw_client.get_metric_statistics(**kwargs)
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

        return {"api_name": api_name, "stage": stage, "metrics": result}
    except ClientError as e:
        return {"error": str(e)}
