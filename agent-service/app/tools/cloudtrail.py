from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def lookup_cloudtrail_events(
    lookup_attributes: Optional[list[dict]] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    max_results: int = 50,
) -> dict:
    """Look up CloudTrail management events with optional attribute filters.

    Args:
        lookup_attributes: Optional list of {AttributeKey, AttributeValue} dicts.
                          Valid keys: EventId, EventName, ReadOnly, Username,
                          ResourceType, ResourceName, EventSource, AccessKeyId.
        start_time: Optional ISO 8601 start time string.
        end_time: Optional ISO 8601 end time string.
        max_results: Maximum number of events to return (default 50, max 50).

    Returns a dict with 'events' list including EventName, EventTime, Username,
    Resources, and CloudTrailEvent (raw JSON string).
    """
    try:
        client = boto3.client("cloudtrail", region_name=settings.aws_region)
        kwargs: dict = {"MaxResults": min(max_results, 50)}
        if lookup_attributes:
            kwargs["LookupAttributes"] = lookup_attributes
        if start_time:
            kwargs["StartTime"] = datetime.fromisoformat(start_time)
        if end_time:
            kwargs["EndTime"] = datetime.fromisoformat(end_time)

        events = []
        paginator = client.get_paginator("lookup_events")
        for page in paginator.paginate(**kwargs):
            for event in page.get("Events", []):
                events.append(
                    {
                        "EventId": event.get("EventId"),
                        "EventName": event.get("EventName"),
                        "EventTime": event.get("EventTime", "").isoformat()
                        if event.get("EventTime")
                        else None,
                        "EventSource": event.get("EventSource"),
                        "Username": event.get("Username"),
                        "Resources": event.get("Resources", []),
                        "CloudTrailEvent": event.get("CloudTrailEvent"),
                    }
                )
            if len(events) >= max_results:
                break

        return {"events": events[:max_results]}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_trail_status(trail_name: str) -> dict:
    """Get the status of a CloudTrail trail including latest delivery and error info.

    Args:
        trail_name: The trail name or ARN.

    Returns a dict with IsLogging, LatestDeliveryTime, LatestDeliveryError,
    LatestNotificationTime, and LatestCloudWatchLogsDeliveryTime.
    """
    try:
        client = boto3.client("cloudtrail", region_name=settings.aws_region)
        response = client.get_trail_status(Name=trail_name)
        return {
            "IsLogging": response.get("IsLogging"),
            "LatestDeliveryTime": response.get("LatestDeliveryTime", "").isoformat()
            if response.get("LatestDeliveryTime")
            else None,
            "LatestDeliveryError": response.get("LatestDeliveryError"),
            "LatestNotificationTime": response.get("LatestNotificationTime", "").isoformat()
            if response.get("LatestNotificationTime")
            else None,
            "LatestNotificationError": response.get("LatestNotificationError"),
            "LatestCloudWatchLogsDeliveryTime": response.get("LatestCloudWatchLogsDeliveryTime", "").isoformat()
            if response.get("LatestCloudWatchLogsDeliveryTime")
            else None,
            "LatestCloudWatchLogsDeliveryError": response.get("LatestCloudWatchLogsDeliveryError"),
            "StartLoggingTime": response.get("StartLoggingTime", "").isoformat()
            if response.get("StartLoggingTime")
            else None,
        }
    except ClientError as e:
        return {"error": str(e)}
