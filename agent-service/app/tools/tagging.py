from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_tagged_resources(
    tag_filters: Optional[list[dict]] = None,
    resource_type_filters: Optional[list[str]] = None,
    max_results: int = 100,
) -> dict:
    """List AWS resources filtered by tags using the Resource Groups Tagging API.

    Args:
        tag_filters: Optional list of {Key, Values} tag filter dicts.
                    Example: [{"Key": "Environment", "Values": ["prod"]}]
        resource_type_filters: Optional list of resource type strings to filter.
                               Example: ['ec2:instance', 'rds:db', 'lambda:function']
        max_results: Maximum number of resources to return (default 100).

    Returns a dict with 'resources' list of {ResourceARN, Tags}.
    """
    try:
        client = boto3.client("resourcegroupstaggingapi", region_name=settings.aws_region)
        kwargs: dict = {}
        if tag_filters:
            kwargs["TagFilters"] = tag_filters
        if resource_type_filters:
            kwargs["ResourceTypeFilters"] = resource_type_filters

        resources = []
        paginator = client.get_paginator("get_resources")
        for page in paginator.paginate(**kwargs):
            for resource in page.get("ResourceTagMappingList", []):
                resources.append(
                    {
                        "ResourceARN": resource.get("ResourceARN"),
                        "Tags": {tag["Key"]: tag["Value"] for tag in resource.get("Tags", [])},
                    }
                )
            if len(resources) >= max_results:
                break

        return {"resources": resources[:max_results]}
    except ClientError as e:
        return {"error": str(e)}
