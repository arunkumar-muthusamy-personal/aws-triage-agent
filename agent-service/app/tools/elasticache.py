from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def describe_cache_clusters(
    cache_cluster_id: Optional[str] = None,
    show_cache_node_info: bool = True,
) -> dict:
    """Describe ElastiCache cache clusters.

    Args:
        cache_cluster_id: Optional specific cluster ID to describe.
        show_cache_node_info: Whether to include node info (default True).

    Returns a dict with 'cache_clusters' list.
    """
    try:
        client = boto3.client("elasticache", region_name=settings.aws_region)
        kwargs: dict = {"ShowCacheNodeInfo": show_cache_node_info}
        if cache_cluster_id:
            kwargs["CacheClusterId"] = cache_cluster_id

        clusters = []
        paginator = client.get_paginator("describe_cache_clusters")
        for page in paginator.paginate(**kwargs):
            clusters.extend(page.get("CacheClusters", []))

        return {"cache_clusters": clusters}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_elasticache_metrics(
    cache_cluster_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    period: int = 300,
) -> dict:
    """Retrieve CloudWatch metrics for an ElastiCache cluster.

    Fetches: CurrConnections, Evictions, CacheHits, CacheMisses, FreeableMemory.

    Args:
        cache_cluster_id: The ElastiCache cluster ID.
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

        dimensions = [{"Name": "CacheClusterId", "Value": cache_cluster_id}]

        metrics_config = [
            ("CurrConnections", ["Average", "Maximum"]),
            ("Evictions", ["Sum"]),
            ("CacheHits", ["Sum"]),
            ("CacheMisses", ["Sum"]),
            ("FreeableMemory", ["Average", "Minimum"]),
        ]

        result: dict = {}
        for metric_name, statistics in metrics_config:
            response = cw_client.get_metric_statistics(
                Namespace="AWS/ElastiCache",
                MetricName=metric_name,
                Dimensions=dimensions,
                StartTime=start,
                EndTime=end,
                Period=period,
                Statistics=statistics,
            )
            result[metric_name] = sorted(
                [
                    {
                        "timestamp": dp["Timestamp"].isoformat(),
                        **{s: dp.get(s) for s in statistics if s in dp},
                    }
                    for dp in response.get("Datapoints", [])
                ],
                key=lambda x: x["timestamp"],
            )

        return {"cache_cluster_id": cache_cluster_id, "metrics": result}
    except ClientError as e:
        return {"error": str(e)}
