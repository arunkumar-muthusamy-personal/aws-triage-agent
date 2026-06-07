from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_queues(queue_name_prefix: Optional[str] = None) -> dict:
    """List SQS queue URLs, optionally filtered by a name prefix.

    Args:
        queue_name_prefix: Optional prefix to filter queue names.

    Returns a dict with 'queue_urls' list.
    """
    try:
        client = boto3.client("sqs", region_name=settings.aws_region)
        kwargs: dict = {}
        if queue_name_prefix:
            kwargs["QueueNamePrefix"] = queue_name_prefix

        queue_urls = []
        paginator = client.get_paginator("list_queues")
        for page in paginator.paginate(**kwargs):
            queue_urls.extend(page.get("QueueUrls", []))

        return {"queue_urls": queue_urls}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_queue_attributes(queue_url: str) -> dict:
    """Get all attributes of an SQS queue.

    Args:
        queue_url: The SQS queue URL.

    Returns a dict with all queue attributes including ApproximateNumberOfMessages,
    VisibilityTimeout, MessageRetentionPeriod, RedrivePolicy, etc.
    """
    try:
        client = boto3.client("sqs", region_name=settings.aws_region)
        response = client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=["All"],
        )
        return {"queue_url": queue_url, "attributes": response.get("Attributes", {})}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_sqs_dead_letter_source_queues(queue_url: str) -> dict:
    """List source queues that have this SQS queue configured as a dead-letter queue.

    Args:
        queue_url: The URL of the dead-letter queue.

    Returns a dict with 'source_queue_urls' list.
    """
    try:
        client = boto3.client("sqs", region_name=settings.aws_region)
        source_urls = []
        paginator = client.get_paginator("list_dead_letter_source_queues")
        for page in paginator.paginate(QueueUrl=queue_url):
            source_urls.extend(page.get("queueUrls", []))
        return {"dead_letter_queue_url": queue_url, "source_queue_urls": source_urls}
    except ClientError as e:
        return {"error": str(e)}
