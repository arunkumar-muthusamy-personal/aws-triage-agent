from typing import Optional

import boto3
from botocore.exceptions import ClientError
from langchain_core.tools import tool

from app.config import settings


@tool
def list_glue_jobs(max_results: int = 100) -> dict:
    """List AWS Glue ETL jobs in the account/region.

    Args:
        max_results: Maximum number of jobs to return (default 100).

    Returns a dict with 'jobs' list of {Name, Role, CreatedOn, LastModifiedOn, Timeout}.
    """
    try:
        client = boto3.client("glue", region_name=settings.aws_region)
        jobs = []
        paginator = client.get_paginator("get_jobs")
        for page in paginator.paginate():
            for job in page.get("Jobs", []):
                jobs.append(
                    {
                        "Name": job.get("Name"),
                        "Role": job.get("Role"),
                        "Command": job.get("Command", {}).get("Name"),
                        "GlueVersion": job.get("GlueVersion"),
                        "MaxCapacity": job.get("MaxCapacity"),
                        "Timeout": job.get("Timeout"),
                        "CreatedOn": job.get("CreatedOn", "").isoformat()
                        if job.get("CreatedOn")
                        else None,
                        "LastModifiedOn": job.get("LastModifiedOn", "").isoformat()
                        if job.get("LastModifiedOn")
                        else None,
                    }
                )
            if len(jobs) >= max_results:
                break

        return {"jobs": jobs[:max_results]}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_glue_job_runs(
    job_name: str,
    max_results: int = 20,
) -> dict:
    """Get recent run history for a Glue job.

    Args:
        job_name: The Glue job name.
        max_results: Maximum number of runs to return (default 20).

    Returns a dict with 'job_runs' list including status, start/end times, and error messages.
    """
    try:
        client = boto3.client("glue", region_name=settings.aws_region)
        runs = []
        paginator = client.get_paginator("get_job_runs")
        for page in paginator.paginate(JobName=job_name):
            for run in page.get("JobRuns", []):
                runs.append(
                    {
                        "Id": run.get("Id"),
                        "JobName": run.get("JobName"),
                        "JobRunState": run.get("JobRunState"),
                        "StartedOn": run.get("StartedOn", "").isoformat()
                        if run.get("StartedOn")
                        else None,
                        "CompletedOn": run.get("CompletedOn", "").isoformat()
                        if run.get("CompletedOn")
                        else None,
                        "ExecutionTime": run.get("ExecutionTime"),
                        "ErrorMessage": run.get("ErrorMessage"),
                        "Attempt": run.get("Attempt"),
                        "GlueVersion": run.get("GlueVersion"),
                    }
                )
            if len(runs) >= max_results:
                break

        return {"job_name": job_name, "job_runs": runs[:max_results]}
    except ClientError as e:
        return {"error": str(e)}


@tool
def get_glue_crawlers(crawler_name: Optional[str] = None) -> dict:
    """List or describe Glue crawlers.

    Args:
        crawler_name: Optional specific crawler name to describe.

    Returns a dict with 'crawlers' list including state, last_crawl info, and schedule.
    """
    try:
        client = boto3.client("glue", region_name=settings.aws_region)

        if crawler_name:
            response = client.get_crawler(Name=crawler_name)
            crawlers = [response.get("Crawler", {})]
        else:
            crawlers = []
            paginator = client.get_paginator("get_crawlers")
            for page in paginator.paginate():
                crawlers.extend(page.get("Crawlers", []))

        result = []
        for c in crawlers:
            result.append(
                {
                    "Name": c.get("Name"),
                    "Role": c.get("Role"),
                    "State": c.get("State"),
                    "DatabaseName": c.get("DatabaseName"),
                    "Schedule": c.get("Schedule", {}).get("ScheduleExpression"),
                    "LastCrawl": {
                        "Status": c.get("LastCrawl", {}).get("Status"),
                        "ErrorMessage": c.get("LastCrawl", {}).get("ErrorMessage"),
                        "StartTime": c.get("LastCrawl", {}).get("StartTime", "").isoformat()
                        if c.get("LastCrawl", {}).get("StartTime")
                        else None,
                    }
                    if c.get("LastCrawl")
                    else None,
                    "CreationTime": c.get("CreationTime", "").isoformat()
                    if c.get("CreationTime")
                    else None,
                }
            )

        return {"crawlers": result}
    except ClientError as e:
        return {"error": str(e)}
