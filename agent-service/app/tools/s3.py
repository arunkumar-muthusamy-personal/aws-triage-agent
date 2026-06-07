import json
from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_buckets() -> dict:
    """List all S3 buckets in the account.

    Returns a dict with 'buckets' list of {Name, CreationDate}.
    """
    try:
        client = boto3.client("s3", region_name=settings.aws_region)
        response = client.list_buckets()
        buckets = [
            {
                "Name": b["Name"],
                "CreationDate": b["CreationDate"].isoformat() if b.get("CreationDate") else None,
            }
            for b in response.get("Buckets", [])
        ]
        return {"buckets": buckets}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_bucket_metadata(bucket_name: str) -> dict:
    """Retrieve metadata for an S3 bucket: versioning, encryption, public access block,
    replication, and lifecycle rules.

    Args:
        bucket_name: The S3 bucket name.

    Returns a dict aggregating all metadata.
    """
    try:
        client = boto3.client("s3", region_name=settings.aws_region)
        result: dict = {"bucket_name": bucket_name}

        # Versioning
        try:
            v = client.get_bucket_versioning(Bucket=bucket_name)
            result["versioning"] = v.get("Status", "Disabled")
        except ClientError:
            result["versioning"] = "unknown"

        # Encryption
        try:
            enc = client.get_bucket_encryption(Bucket=bucket_name)
            result["encryption"] = enc.get("ServerSideEncryptionConfiguration", {})
        except ClientError:
            result["encryption"] = None

        # Public access block
        try:
            pab = client.get_public_access_block(Bucket=bucket_name)
            result["public_access_block"] = pab.get("PublicAccessBlockConfiguration", {})
        except ClientError:
            result["public_access_block"] = None

        # Replication
        try:
            rep = client.get_bucket_replication(Bucket=bucket_name)
            result["replication"] = rep.get("ReplicationConfiguration", {})
        except ClientError:
            result["replication"] = None

        # Lifecycle
        try:
            lc = client.get_bucket_lifecycle_configuration(Bucket=bucket_name)
            result["lifecycle_rules"] = lc.get("Rules", [])
        except ClientError:
            result["lifecycle_rules"] = []

        return result
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_bucket_policy(bucket_name: str) -> dict:
    """Retrieve the bucket policy (as parsed JSON) and public access block for an S3 bucket.

    Args:
        bucket_name: The S3 bucket name.

    Returns a dict with 'policy' (parsed JSON or None) and 'public_access_block'.
    """
    try:
        client = boto3.client("s3", region_name=settings.aws_region)
        result: dict = {"bucket_name": bucket_name}

        try:
            policy_resp = client.get_bucket_policy(Bucket=bucket_name)
            result["policy"] = json.loads(policy_resp["Policy"])
        except ClientError as e:
            if "NoSuchBucketPolicy" in str(e):
                result["policy"] = None
            else:
                result["policy_error"] = str(e)

        try:
            pab = client.get_public_access_block(Bucket=bucket_name)
            result["public_access_block"] = pab.get("PublicAccessBlockConfiguration", {})
        except ClientError:
            result["public_access_block"] = None

        return result
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_s3_metrics(
    bucket_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    period: int = 86400,
) -> dict:
    """Retrieve CloudWatch metrics for an S3 bucket.

    Fetches: BucketSizeBytes, NumberOfObjects, AllRequests, 4xxErrors, 5xxErrors.

    Args:
        bucket_name: The S3 bucket name.
        start_time: ISO 8601 start time (defaults to 2 days ago).
        end_time: ISO 8601 end time (defaults to now).
        period: Period in seconds (default 86400 = 1 day for storage metrics).

    Returns a dict with per-metric datapoints.
    """
    try:
        cw_client = boto3.client("cloudwatch", region_name=settings.aws_region)
        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(start_time) if start_time else now - timedelta(days=2)
        end = datetime.fromisoformat(end_time) if end_time else now

        metrics_config = [
            ("BucketSizeBytes", [{"Name": "BucketName", "Value": bucket_name}, {"Name": "StorageType", "Value": "StandardStorage"}], ["Average"]),
            ("NumberOfObjects", [{"Name": "BucketName", "Value": bucket_name}, {"Name": "StorageType", "Value": "AllStorageTypes"}], ["Average"]),
            ("AllRequests", [{"Name": "BucketName", "Value": bucket_name}, {"Name": "FilterId", "Value": "EntireBucket"}], ["Sum"]),
            ("4xxErrors", [{"Name": "BucketName", "Value": bucket_name}, {"Name": "FilterId", "Value": "EntireBucket"}], ["Sum"]),
            ("5xxErrors", [{"Name": "BucketName", "Value": bucket_name}, {"Name": "FilterId", "Value": "EntireBucket"}], ["Sum"]),
        ]

        result: dict = {}
        for metric_name, dimensions, statistics in metrics_config:
            try:
                response = cw_client.get_metric_statistics(
                    Namespace="AWS/S3",
                    MetricName=metric_name,
                    Dimensions=dimensions,
                    StartTime=start,
                    EndTime=end,
                    Period=period,
                    Statistics=statistics,
                )
                result[metric_name] = sorted(
                    [
                        {"timestamp": dp["Timestamp"].isoformat(), **{s: dp.get(s) for s in statistics}}
                        for dp in response.get("Datapoints", [])
                    ],
                    key=lambda x: x["timestamp"],
                )
            except ClientError:
                result[metric_name] = []

        return {"bucket_name": bucket_name, "metrics": result}
    except ClientError as e:
        return {"error": str(e)}
