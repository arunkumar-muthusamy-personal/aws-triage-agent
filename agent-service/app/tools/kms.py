import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_kms_keys() -> dict:
    """List all KMS keys in the account/region.

    Returns a dict with 'keys' list of {KeyId, KeyArn}.
    """
    try:
        client = boto3.client("kms", region_name=settings.aws_region)
        keys = []
        paginator = client.get_paginator("list_keys")
        for page in paginator.paginate():
            keys.extend(page.get("Keys", []))
        return {"keys": keys}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_kms_key(key_id: str) -> dict:
    """Describe a KMS key including its metadata and rotation status.

    Args:
        key_id: The KMS key ID or ARN.

    Returns a dict with key metadata and rotation status.
    """
    try:
        client = boto3.client("kms", region_name=settings.aws_region)

        desc_response = client.describe_key(KeyId=key_id)
        key_metadata = desc_response.get("KeyMetadata", {})

        rotation_status: dict = {}
        try:
            rot_response = client.get_key_rotation_status(KeyId=key_id)
            rotation_status = {
                "KeyRotationEnabled": rot_response.get("KeyRotationEnabled"),
            }
        except ClientError:
            # AWS-managed keys don't support get_key_rotation_status
            rotation_status = {"KeyRotationEnabled": None, "note": "Could not retrieve rotation status"}

        return {
            "KeyId": key_metadata.get("KeyId"),
            "KeyArn": key_metadata.get("Arn"),
            "KeyState": key_metadata.get("KeyState"),
            "KeyUsage": key_metadata.get("KeyUsage"),
            "KeySpec": key_metadata.get("KeySpec"),
            "Origin": key_metadata.get("Origin"),
            "Description": key_metadata.get("Description"),
            "Enabled": key_metadata.get("Enabled"),
            "CreationDate": key_metadata.get("CreationDate", "").isoformat()
            if key_metadata.get("CreationDate")
            else None,
            "DeletionDate": key_metadata.get("DeletionDate", "").isoformat()
            if key_metadata.get("DeletionDate")
            else None,
            "KeyManager": key_metadata.get("KeyManager"),
            "MultiRegion": key_metadata.get("MultiRegion"),
            **rotation_status,
        }
    except ClientError as e:
        return {"error": str(e)}
