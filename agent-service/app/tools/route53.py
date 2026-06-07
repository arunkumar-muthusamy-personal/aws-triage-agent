from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_hosted_zones() -> dict:
    """List all Route 53 hosted zones in the account.

    Returns a dict with 'hosted_zones' list of {Id, Name, Type (public/private),
    RecordCount, Comment}.
    """
    try:
        client = boto3.client("route53", region_name=settings.aws_region)
        zones = []
        paginator = client.get_paginator("list_hosted_zones")
        for page in paginator.paginate():
            for zone in page.get("HostedZones", []):
                zones.append(
                    {
                        "Id": zone.get("Id"),
                        "Name": zone.get("Name"),
                        "Private": zone.get("Config", {}).get("PrivateZone", False),
                        "RecordCount": zone.get("ResourceRecordSetCount"),
                        "Comment": zone.get("Config", {}).get("Comment"),
                    }
                )
        return {"hosted_zones": zones}
    except ClientError as e:
        return {"error": str(e)}


@tool
def list_resource_record_sets(
    hosted_zone_id: str,
    record_name: Optional[str] = None,
    record_type: Optional[str] = None,
    max_items: int = 100,
) -> dict:
    """List resource record sets in a Route 53 hosted zone.

    Args:
        hosted_zone_id: The hosted zone ID (e.g. 'Z1234567890').
        record_name: Optional record name to start listing from.
        record_type: Optional record type filter (e.g. 'A', 'CNAME', 'MX').
        max_items: Maximum number of records to return (default 100).

    Returns a dict with 'record_sets' list.
    """
    try:
        client = boto3.client("route53", region_name=settings.aws_region)
        kwargs: dict = {"HostedZoneId": hosted_zone_id, "MaxItems": str(max_items)}
        if record_name:
            kwargs["StartRecordName"] = record_name
        if record_type:
            kwargs["StartRecordType"] = record_type

        record_sets = []
        while True:
            response = client.list_resource_record_sets(**kwargs)
            record_sets.extend(response.get("ResourceRecordSets", []))
            if not response.get("IsTruncated") or len(record_sets) >= max_items:
                break
            kwargs["StartRecordName"] = response.get("NextRecordName")
            kwargs["StartRecordType"] = response.get("NextRecordType")

        return {"hosted_zone_id": hosted_zone_id, "record_sets": record_sets[:max_items]}
    except ClientError as e:
        return {"error": str(e)}
