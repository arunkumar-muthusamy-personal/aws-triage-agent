from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_secrets(
    name_prefix: Optional[str] = None,
    max_results: int = 100,
) -> dict:
    """List Secrets Manager secrets — metadata ONLY. Secret values are NEVER fetched.

    Args:
        name_prefix: Optional prefix to filter secret names.
        max_results: Maximum number of secrets to return (default 100).

    Returns a dict with 'secrets' list of metadata: {Name, ARN, Description,
    LastChangedDate, LastAccessedDate, RotationEnabled, Tags}.
    NOTE: get_secret_value is intentionally never called. Only metadata is returned.
    """
    try:
        client = boto3.client("secretsmanager", region_name=settings.aws_region)
        kwargs: dict = {"MaxResults": min(max_results, 100)}
        if name_prefix:
            kwargs["Filters"] = [{"Key": "name", "Values": [name_prefix]}]

        secrets = []
        paginator = client.get_paginator("list_secrets")
        for page in paginator.paginate(**kwargs):
            for secret in page.get("SecretList", []):
                secrets.append(
                    {
                        "Name": secret.get("Name"),
                        "ARN": secret.get("ARN"),
                        "Description": secret.get("Description"),
                        "LastChangedDate": secret.get("LastChangedDate", "").isoformat()
                        if secret.get("LastChangedDate")
                        else None,
                        "LastAccessedDate": secret.get("LastAccessedDate", "").isoformat()
                        if secret.get("LastAccessedDate")
                        else None,
                        "RotationEnabled": secret.get("RotationEnabled"),
                        "RotationRules": secret.get("RotationRules"),
                        "Tags": secret.get("Tags", []),
                        "KmsKeyId": secret.get("KmsKeyId"),
                    }
                )
            if len(secrets) >= max_results:
                break

        return {"secrets": secrets[:max_results]}
    except ClientError as e:
        return {"error": str(e)}
