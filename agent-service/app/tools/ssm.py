from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def describe_ssm_parameters(
    parameter_filters: Optional[list[dict]] = None,
    max_results: int = 50,
) -> dict:
    """List SSM Parameter Store parameters (metadata only, no values).

    Args:
        parameter_filters: Optional list of {Key, Option, Values} filter dicts.
                          Example: [{"Key": "Path", "Option": "Recursive", "Values": ["/myapp"]}]
        max_results: Maximum number of parameters to return (default 50).

    Returns a dict with 'parameters' list of metadata (no values).
    """
    try:
        client = boto3.client("ssm", region_name=settings.aws_region)
        kwargs: dict = {}
        if parameter_filters:
            kwargs["ParameterFilters"] = parameter_filters

        parameters = []
        paginator = client.get_paginator("describe_parameters")
        for page in paginator.paginate(**kwargs):
            for param in page.get("Parameters", []):
                parameters.append(
                    {
                        "Name": param.get("Name"),
                        "Type": param.get("Type"),
                        "Description": param.get("Description"),
                        "Version": param.get("Version"),
                        "LastModifiedDate": param.get("LastModifiedDate", "").isoformat()
                        if param.get("LastModifiedDate")
                        else None,
                        "LastModifiedUser": param.get("LastModifiedUser"),
                        "Tier": param.get("Tier"),
                        "DataType": param.get("DataType"),
                    }
                )
            if len(parameters) >= max_results:
                break

        return {"parameters": parameters[:max_results]}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_parameters_by_path(
    path: str,
    recursive: bool = True,
    max_results: int = 50,
) -> dict:
    """Retrieve SSM parameters under a path hierarchy.

    SecureString parameter values are REDACTED and replaced with '[REDACTED]'.
    String and StringList parameter values are returned as-is.
    WithDecryption is always False — SecureString values will appear as
    encrypted ciphertext and are replaced with '[REDACTED]' for safety.

    Args:
        path: The SSM parameter path prefix (e.g. '/myapp/prod/').
        recursive: Whether to retrieve all parameters within the hierarchy (default True).
        max_results: Maximum number of parameters to return (default 50).

    Returns a dict with 'parameters' list of {Name, Type, Value (redacted for SecureString)}.
    """
    try:
        client = boto3.client("ssm", region_name=settings.aws_region)
        parameters = []
        paginator = client.get_paginator("get_parameters_by_path")
        for page in paginator.paginate(
            Path=path,
            Recursive=recursive,
            WithDecryption=False,
        ):
            for param in page.get("Parameters", []):
                value = "[REDACTED]" if param.get("Type") == "SecureString" else param.get("Value")
                parameters.append(
                    {
                        "Name": param.get("Name"),
                        "Type": param.get("Type"),
                        "Value": value,
                        "Version": param.get("Version"),
                        "LastModifiedDate": param.get("LastModifiedDate", "").isoformat()
                        if param.get("LastModifiedDate")
                        else None,
                        "ARN": param.get("ARN"),
                        "DataType": param.get("DataType"),
                    }
                )
            if len(parameters) >= max_results:
                break

        return {"path": path, "parameters": parameters[:max_results]}
    except ClientError as e:
        return {"error": str(e)}
