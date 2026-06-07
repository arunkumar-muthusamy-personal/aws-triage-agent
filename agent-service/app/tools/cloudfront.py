import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_distributions() -> dict:
    """List all CloudFront distributions.

    Returns a dict with 'distributions' list including Id, DomainName, Status,
    Origins, and Aliases.
    """
    try:
        client = boto3.client("cloudfront", region_name=settings.aws_region)
        distributions = []
        paginator = client.get_paginator("list_distributions")
        for page in paginator.paginate():
            dist_list = page.get("DistributionList", {})
            for item in dist_list.get("Items", []):
                distributions.append(
                    {
                        "Id": item.get("Id"),
                        "DomainName": item.get("DomainName"),
                        "Status": item.get("Status"),
                        "Enabled": item.get("Enabled"),
                        "Origins": item.get("Origins", {}).get("Items", []),
                        "Aliases": item.get("Aliases", {}).get("Items", []),
                        "LastModifiedTime": item.get("LastModifiedTime", "").isoformat()
                        if item.get("LastModifiedTime")
                        else None,
                    }
                )
        return {"distributions": distributions}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_distribution_config(distribution_id: str) -> dict:
    """Get the configuration for a specific CloudFront distribution.

    Args:
        distribution_id: The CloudFront distribution ID.

    Returns a dict with the distribution configuration.
    """
    try:
        client = boto3.client("cloudfront", region_name=settings.aws_region)
        response = client.get_distribution_config(Id=distribution_id)
        return {
            "distribution_id": distribution_id,
            "etag": response.get("ETag"),
            "config": response.get("DistributionConfig", {}),
        }
    except ClientError as e:
        return {"error": str(e)}
