from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_certificates(
    certificate_statuses: Optional[list[str]] = None,
) -> dict:
    """List ACM certificates in the account/region.

    Args:
        certificate_statuses: Optional list of status filters, e.g.
                              ['ISSUED', 'PENDING_VALIDATION', 'EXPIRED'].

    Returns a dict with 'certificates' list of {CertificateArn, DomainName}.
    """
    try:
        client = boto3.client("acm", region_name=settings.aws_region)
        kwargs: dict = {}
        if certificate_statuses:
            kwargs["CertificateStatuses"] = certificate_statuses

        certificates = []
        paginator = client.get_paginator("list_certificates")
        for page in paginator.paginate(**kwargs):
            certificates.extend(page.get("CertificateSummaryList", []))

        return {"certificates": certificates}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_certificate(certificate_arn: str) -> dict:
    """Describe an ACM certificate including its status, domains, and expiry.

    Args:
        certificate_arn: The ACM certificate ARN.

    Returns a dict with certificate details including DomainName, Status,
    NotAfter (expiry), SubjectAlternativeNames, and InUseBy.
    """
    try:
        client = boto3.client("acm", region_name=settings.aws_region)
        response = client.describe_certificate(CertificateArn=certificate_arn)
        cert = response.get("Certificate", {})

        return {
            "CertificateArn": cert.get("CertificateArn"),
            "DomainName": cert.get("DomainName"),
            "SubjectAlternativeNames": cert.get("SubjectAlternativeNames", []),
            "Status": cert.get("Status"),
            "Type": cert.get("Type"),
            "Issuer": cert.get("Issuer"),
            "IssuedAt": cert.get("IssuedAt", "").isoformat() if cert.get("IssuedAt") else None,
            "NotBefore": cert.get("NotBefore", "").isoformat() if cert.get("NotBefore") else None,
            "NotAfter": cert.get("NotAfter", "").isoformat() if cert.get("NotAfter") else None,
            "InUseBy": cert.get("InUseBy", []),
            "RenewalEligibility": cert.get("RenewalEligibility"),
            "RenewalSummary": cert.get("RenewalSummary", {}),
            "DomainValidationOptions": cert.get("DomainValidationOptions", []),
        }
    except ClientError as e:
        return {"error": str(e)}
