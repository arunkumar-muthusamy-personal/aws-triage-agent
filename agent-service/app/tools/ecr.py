from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_repositories(registry_id: Optional[str] = None) -> dict:
    """List ECR repositories in the account/region.

    Args:
        registry_id: Optional registry ID (AWS account ID). Defaults to caller's account.

    Returns a dict with 'repositories' list of {repositoryName, repositoryUri,
    createdAt, imageTagMutability}.
    """
    try:
        client = boto3.client("ecr", region_name=settings.aws_region)
        kwargs: dict = {}
        if registry_id:
            kwargs["registryId"] = registry_id

        repositories = []
        paginator = client.get_paginator("describe_repositories")
        for page in paginator.paginate(**kwargs):
            for repo in page.get("repositories", []):
                repositories.append(
                    {
                        "repositoryName": repo.get("repositoryName"),
                        "repositoryUri": repo.get("repositoryUri"),
                        "registryId": repo.get("registryId"),
                        "imageTagMutability": repo.get("imageTagMutability"),
                        "imageScanningConfiguration": repo.get("imageScanningConfiguration", {}),
                        "createdAt": repo.get("createdAt", "").isoformat()
                        if repo.get("createdAt")
                        else None,
                    }
                )

        return {"repositories": repositories}
    except ClientError as e:
        return {"error": str(e)}


@tool
def describe_images(
    repository_name: str,
    registry_id: Optional[str] = None,
    image_tag: Optional[str] = None,
    max_results: int = 20,
) -> dict:
    """Describe images in an ECR repository.

    Args:
        repository_name: The ECR repository name.
        registry_id: Optional registry ID (AWS account ID).
        image_tag: Optional image tag to filter by.
        max_results: Maximum number of images to return (default 20).

    Returns a dict with 'images' list including digest, tags, pushed date, and scan findings summary.
    """
    try:
        client = boto3.client("ecr", region_name=settings.aws_region)
        kwargs: dict = {"repositoryName": repository_name, "maxResults": max_results}
        if registry_id:
            kwargs["registryId"] = registry_id
        if image_tag:
            kwargs["imageIds"] = [{"imageTag": image_tag}]

        images = []
        paginator = client.get_paginator("describe_images")
        for page in paginator.paginate(**kwargs):
            for img in page.get("imageDetails", []):
                images.append(
                    {
                        "imageDigest": img.get("imageDigest"),
                        "imageTags": img.get("imageTags", []),
                        "imageSizeInBytes": img.get("imageSizeInBytes"),
                        "imagePushedAt": img.get("imagePushedAt", "").isoformat()
                        if img.get("imagePushedAt")
                        else None,
                        "imageScanStatus": img.get("imageScanStatus", {}).get("status"),
                        "imageScanFindingsSummary": img.get("imageScanFindingsSummary", {}),
                    }
                )
            if len(images) >= max_results:
                break

        return {"repository_name": repository_name, "images": images[:max_results]}
    except ClientError as e:
        return {"error": str(e)}
