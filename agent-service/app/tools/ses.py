import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def get_send_statistics() -> dict:
    """Retrieve SES email sending statistics for the last 14 days.

    Returns a dict with 'send_data_points' list of {Timestamp, DeliveryAttempts,
    Bounces, Complaints, Rejects}.
    """
    try:
        client = boto3.client("ses", region_name=settings.aws_region)
        response = client.get_send_statistics()
        data_points = [
            {
                "Timestamp": dp.get("Timestamp", "").isoformat() if dp.get("Timestamp") else None,
                "DeliveryAttempts": dp.get("DeliveryAttempts"),
                "Bounces": dp.get("Bounces"),
                "Complaints": dp.get("Complaints"),
                "Rejects": dp.get("Rejects"),
            }
            for dp in response.get("SendDataPoints", [])
        ]
        return {"send_data_points": sorted(data_points, key=lambda x: x.get("Timestamp") or "")}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_account_sending_enabled() -> dict:
    """Check whether SES sending is enabled for the account and get sending quota.

    Returns a dict with 'SendingEnabled', 'Max24HourSend', 'MaxSendRate',
    and 'SentLast24Hours'.
    """
    try:
        client = boto3.client("ses", region_name=settings.aws_region)

        quota_response = client.get_send_quota()

        # Check account-level sending enabled status
        try:
            enabled_response = client.get_account_sending_enabled()
            sending_enabled = enabled_response.get("Enabled", True)
        except ClientError:
            sending_enabled = None

        return {
            "SendingEnabled": sending_enabled,
            "Max24HourSend": quota_response.get("Max24HourSend"),
            "MaxSendRate": quota_response.get("MaxSendRate"),
            "SentLast24Hours": quota_response.get("SentLast24Hours"),
        }
    except ClientError as e:
        return {"error": str(e)}
