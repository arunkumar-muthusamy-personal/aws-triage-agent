from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_topics() -> dict:
    """List all SNS topic ARNs in the account/region.

    Returns a dict with 'topic_arns' list.
    """
    try:
        client = boto3.client("sns", region_name=settings.aws_region)
        topic_arns = []
        paginator = client.get_paginator("list_topics")
        for page in paginator.paginate():
            for topic in page.get("Topics", []):
                topic_arns.append(topic["TopicArn"])
        return {"topic_arns": topic_arns}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_topic_attributes(topic_arn: str) -> dict:
    """Get attributes of an SNS topic.

    Args:
        topic_arn: The ARN of the SNS topic.

    Returns a dict with all topic attributes including DisplayName,
    SubscriptionsConfirmed, SubscriptionsPending, Policy, etc.
    """
    try:
        client = boto3.client("sns", region_name=settings.aws_region)
        response = client.get_topic_attributes(TopicArn=topic_arn)
        return {"topic_arn": topic_arn, "attributes": response.get("Attributes", {})}
    except ClientError as e:
        return {"error": str(e)}
