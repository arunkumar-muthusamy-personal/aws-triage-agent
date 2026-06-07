from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def describe_db_instances(db_instance_identifier: Optional[str] = None) -> dict:
    """Describe RDS DB instances.

    Args:
        db_instance_identifier: Optional specific DB instance identifier.

    Returns a dict with 'db_instances' list.
    """
    try:
        client = boto3.client("rds", region_name=settings.aws_region)
        kwargs: dict = {}
        if db_instance_identifier:
            kwargs["DBInstanceIdentifier"] = db_instance_identifier

        instances = []
        paginator = client.get_paginator("describe_db_instances")
        for page in paginator.paginate(**kwargs):
            instances.extend(page.get("DBInstances", []))

        return {"db_instances": instances}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_db_clusters(db_cluster_identifier: Optional[str] = None) -> dict:
    """Describe RDS DB clusters (Aurora clusters).

    Args:
        db_cluster_identifier: Optional specific DB cluster identifier.

    Returns a dict with 'db_clusters' list.
    """
    try:
        client = boto3.client("rds", region_name=settings.aws_region)
        kwargs: dict = {}
        if db_cluster_identifier:
            kwargs["DBClusterIdentifier"] = db_cluster_identifier

        clusters = []
        paginator = client.get_paginator("describe_db_clusters")
        for page in paginator.paginate(**kwargs):
            clusters.extend(page.get("DBClusters", []))

        return {"db_clusters": clusters}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_db_events(
    source_identifier: Optional[str] = None,
    source_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    duration: Optional[int] = None,
) -> dict:
    """Retrieve RDS events for a DB instance, cluster, or other source.

    Args:
        source_identifier: Optional source identifier (DB instance or cluster ID).
        source_type: Optional source type, e.g. 'db-instance', 'db-cluster'.
        start_time: Optional ISO 8601 start time string.
        end_time: Optional ISO 8601 end time string.
        duration: Optional duration in minutes (last N minutes of events).

    Returns a dict with 'events' list.
    """
    try:
        client = boto3.client("rds", region_name=settings.aws_region)
        kwargs: dict = {}
        if source_identifier:
            kwargs["SourceIdentifier"] = source_identifier
        if source_type:
            kwargs["SourceType"] = source_type
        if start_time:
            kwargs["StartTime"] = datetime.fromisoformat(start_time)
        if end_time:
            kwargs["EndTime"] = datetime.fromisoformat(end_time)
        if duration:
            kwargs["Duration"] = duration

        events = []
        paginator = client.get_paginator("describe_events")
        for page in paginator.paginate(**kwargs):
            events.extend(page.get("Events", []))

        return {
            "events": [
                {
                    "SourceIdentifier": e.get("SourceIdentifier"),
                    "SourceType": e.get("SourceType"),
                    "Message": e.get("Message"),
                    "Date": e.get("Date", "").isoformat() if e.get("Date") else None,
                    "EventCategories": e.get("EventCategories", []),
                }
                for e in events
            ]
        }
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_rds_log_file_portion(
    db_instance_identifier: str,
    log_file_name: str,
    marker: Optional[str] = None,
    number_of_lines: int = 200,
) -> dict:
    """Download a portion of an RDS DB log file.

    Args:
        db_instance_identifier: The DB instance identifier.
        log_file_name: The name of the log file (e.g. 'error/mysql-error.log').
        marker: Optional marker for pagination (use '0' for beginning).
        number_of_lines: Number of lines to retrieve (default 200).

    Returns a dict with 'log_data' string and 'marker' for pagination.
    """
    try:
        client = boto3.client("rds", region_name=settings.aws_region)
        kwargs: dict = {
            "DBInstanceIdentifier": db_instance_identifier,
            "LogFileName": log_file_name,
            "NumberOfLines": number_of_lines,
        }
        if marker:
            kwargs["Marker"] = marker

        response = client.download_db_log_file_portion(**kwargs)
        return {
            "log_data": response.get("LogFileData", ""),
            "marker": response.get("Marker"),
            "additional_data_pending": response.get("AdditionalDataPending", False),
        }
    except ClientError as e:
        return {"error": str(e)}
