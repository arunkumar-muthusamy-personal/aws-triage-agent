from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_lambda_functions(function_name_prefix: Optional[str] = None) -> dict:
    """List Lambda functions in the account/region.

    Args:
        function_name_prefix: Optional prefix to filter function names.

    Returns a dict with 'functions' list of {FunctionName, Runtime, Handler, MemorySize, Timeout, LastModified}.
    """
    try:
        client = boto3.client("lambda", region_name=settings.aws_region)
        functions = []
        paginator = client.get_paginator("list_functions")
        for page in paginator.paginate():
            for fn in page.get("Functions", []):
                if function_name_prefix and not fn["FunctionName"].startswith(function_name_prefix):
                    continue
                functions.append(
                    {
                        "FunctionName": fn.get("FunctionName"),
                        "FunctionArn": fn.get("FunctionArn"),
                        "Runtime": fn.get("Runtime"),
                        "Handler": fn.get("Handler"),
                        "MemorySize": fn.get("MemorySize"),
                        "Timeout": fn.get("Timeout"),
                        "LastModified": fn.get("LastModified"),
                        "CodeSize": fn.get("CodeSize"),
                    }
                )
        return {"functions": functions}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_function_configuration(function_name: str) -> dict:
    """Get the full configuration for a Lambda function.

    Args:
        function_name: The Lambda function name or ARN.

    Returns a dict with full configuration details including environment variables
    (values masked), VPC config, layers, and concurrency.
    """
    try:
        client = boto3.client("lambda", region_name=settings.aws_region)
        config = client.get_function_configuration(FunctionName=function_name)

        # Mask env var values for security
        env_vars = config.get("Environment", {}).get("Variables", {})
        masked_env = {k: "[REDACTED]" for k in env_vars}

        return {
            "FunctionName": config.get("FunctionName"),
            "FunctionArn": config.get("FunctionArn"),
            "Runtime": config.get("Runtime"),
            "Handler": config.get("Handler"),
            "MemorySize": config.get("MemorySize"),
            "Timeout": config.get("Timeout"),
            "LastModified": config.get("LastModified"),
            "Role": config.get("Role"),
            "Description": config.get("Description"),
            "EnvironmentVariableKeys": list(env_vars.keys()),
            "Environment": {"Variables": masked_env},
            "VpcConfig": config.get("VpcConfig", {}),
            "Layers": config.get("Layers", []),
            "PackageType": config.get("PackageType"),
            "Architectures": config.get("Architectures", []),
            "EphemeralStorage": config.get("EphemeralStorage", {}),
        }
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_lambda_metrics(
    function_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    period: int = 300,
) -> dict:
    """Retrieve CloudWatch metrics for a Lambda function.

    Fetches: Invocations, Errors, Throttles, Duration.

    Args:
        function_name: The Lambda function name.
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

        dimensions = [{"Name": "FunctionName", "Value": function_name}]

        metrics_config = [
            ("Invocations", ["Sum"]),
            ("Errors", ["Sum"]),
            ("Throttles", ["Sum"]),
            ("Duration", ["Average", "Maximum", "p99"]),
        ]

        result: dict = {}
        for metric_name, statistics in metrics_config:
            std_stats = [s for s in statistics if s != "p99"]
            ext_stats = ["p99"] if "p99" in statistics else []
            response = cw_client.get_metric_statistics(
                Namespace="AWS/Lambda",
                MetricName=metric_name,
                Dimensions=dimensions,
                StartTime=start,
                EndTime=end,
                Period=period,
                Statistics=std_stats,
                ExtendedStatistics=ext_stats,
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

        return {"function_name": function_name, "metrics": result}
    except ClientError as e:
        return {"error": str(e)}
