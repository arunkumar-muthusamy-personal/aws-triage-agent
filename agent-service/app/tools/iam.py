from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def get_role(role_name: str) -> dict:
    """Describe an IAM role including attached/inline policies and last used info.

    Policy documents are NOT expanded — only policy names and ARNs are returned.

    Args:
        role_name: The IAM role name.

    Returns a dict with role metadata, attached policies, inline policy names,
    and last used info.
    """
    try:
        client = boto3.client("iam", region_name=settings.aws_region)

        role_response = client.get_role(RoleName=role_name)
        role = role_response.get("Role", {})

        # Attached managed policies
        attached_response = client.list_attached_role_policies(RoleName=role_name)
        attached_policies = [
            {"PolicyName": p["PolicyName"], "PolicyArn": p["PolicyArn"]}
            for p in attached_response.get("AttachedPolicies", [])
        ]

        # Inline policy names only — do not expand documents
        inline_response = client.list_role_policies(RoleName=role_name)
        inline_policy_names = inline_response.get("PolicyNames", [])

        return {
            "RoleName": role.get("RoleName"),
            "RoleId": role.get("RoleId"),
            "Arn": role.get("Arn"),
            "Path": role.get("Path"),
            "Description": role.get("Description"),
            "MaxSessionDuration": role.get("MaxSessionDuration"),
            "CreateDate": role.get("CreateDate", "").isoformat()
            if role.get("CreateDate")
            else None,
            "RoleLastUsed": {
                "LastUsedDate": role.get("RoleLastUsed", {}).get("LastUsedDate", "").isoformat()
                if role.get("RoleLastUsed", {}).get("LastUsedDate")
                else None,
                "Region": role.get("RoleLastUsed", {}).get("Region"),
            },
            "AttachedManagedPolicies": attached_policies,
            "InlinePolicyNames": inline_policy_names,
            "AssumeRolePolicyDocument": role.get("AssumeRolePolicyDocument", {}),
        }
    except ClientError as e:
        return {"error": str(e)}


@tool
def simulate_principal_policy(
    policy_source_arn: str,
    action_names: list[str],
    resource_arns: Optional[list[str]] = None,
    context_entries: Optional[list[dict]] = None,
) -> dict:
    """Simulate IAM policy evaluation to check if a principal can perform actions.

    Args:
        policy_source_arn: ARN of the IAM entity (user, role, group) to simulate.
        action_names: List of action strings to simulate (e.g. ['s3:GetObject']).
        resource_arns: Optional list of resource ARNs to simulate against.
        context_entries: Optional list of context entries for condition evaluation.

    Returns a dict with 'evaluation_results' showing allow/deny decisions per action.
    """
    try:
        client = boto3.client("iam", region_name=settings.aws_region)
        kwargs: dict = {
            "PolicySourceArn": policy_source_arn,
            "ActionNames": action_names,
        }
        if resource_arns:
            kwargs["ResourceArns"] = resource_arns
        if context_entries:
            kwargs["ContextEntries"] = context_entries

        results = []
        paginator = client.get_paginator("simulate_principal_policy")
        for page in paginator.paginate(**kwargs):
            for result in page.get("EvaluationResults", []):
                results.append(
                    {
                        "EvalActionName": result.get("EvalActionName"),
                        "EvalResourceName": result.get("EvalResourceName"),
                        "EvalDecision": result.get("EvalDecision"),
                        "MatchedStatements": result.get("MatchedStatements", []),
                        "MissingContextValues": result.get("MissingContextValues", []),
                    }
                )

        return {"policy_source_arn": policy_source_arn, "evaluation_results": results}
    except ClientError as e:
        return {"error": str(e)}
