from app.tools.cloudwatch_logs import (
    query_cloudwatch_logs,
    list_log_groups,
    get_log_events,
    filter_log_events,
)
from app.tools.cloudwatch_metrics import (
    get_metric_statistics,
    list_metrics,
    describe_alarms,
)
from app.tools.ecs import (
    list_ecs_clusters,
    describe_ecs_services,
    describe_ecs_tasks,
    get_task_stopped_reason,
    describe_ecs_container_instances,
)
from app.tools.ec2 import (
    describe_instances,
    describe_security_groups,
    describe_vpcs,
    describe_subnets,
    describe_autoscaling_groups,
)
from app.tools.rds import (
    describe_db_instances,
    describe_db_clusters,
    describe_db_events,
    get_rds_log_file_portion,
)
from app.tools.dynamodb import (
    describe_dynamodb_table,
    list_dynamodb_tables,
    get_dynamodb_metrics,
)
from app.tools.s3 import (
    list_buckets,
    get_bucket_metadata,
    get_bucket_policy,
    get_s3_metrics,
)
from app.tools.sqs import (
    list_queues,
    get_queue_attributes,
    get_sqs_dead_letter_source_queues,
)
from app.tools.sns import (
    list_topics,
    get_topic_attributes,
)
from app.tools.elb import (
    describe_load_balancers,
    describe_listeners,
    describe_target_groups,
    describe_target_health,
)
from app.tools.apigw import (
    list_rest_apis,
    get_stages,
    get_api_gateway_metrics,
)
from app.tools.cloudfront import (
    list_distributions,
    get_distribution_config,
)
from app.tools.lambda_ import (
    list_lambda_functions,
    get_function_configuration,
    get_lambda_metrics,
)
from app.tools.stepfunctions import (
    list_state_machines,
    describe_state_machine,
    list_executions,
    get_execution_history,
)
from app.tools.glue import (
    list_glue_jobs,
    get_glue_job_runs,
    get_glue_crawlers,
)
from app.tools.elasticache import (
    describe_cache_clusters,
    get_elasticache_metrics,
)
from app.tools.ecr import (
    list_repositories,
    describe_images,
)
from app.tools.kms import (
    list_kms_keys,
    describe_kms_key,
)
from app.tools.secretsmanager import (
    list_secrets,
)
from app.tools.iam import (
    get_role,
    simulate_principal_policy,
)
from app.tools.acm import (
    list_certificates,
    describe_certificate,
)
from app.tools.route53 import (
    list_hosted_zones,
    list_resource_record_sets,
)
from app.tools.ses import (
    get_send_statistics,
    get_account_sending_enabled,
)
from app.tools.cloudtrail import (
    lookup_cloudtrail_events,
    get_trail_status,
)
from app.tools.ssm import (
    describe_ssm_parameters,
    get_parameters_by_path,
)
from app.tools.tagging import (
    list_tagged_resources,
)

ALL_TOOLS = [
    # CloudWatch Logs
    query_cloudwatch_logs,
    list_log_groups,
    get_log_events,
    filter_log_events,
    # CloudWatch Metrics
    get_metric_statistics,
    list_metrics,
    describe_alarms,
    # ECS
    list_ecs_clusters,
    describe_ecs_services,
    describe_ecs_tasks,
    get_task_stopped_reason,
    describe_ecs_container_instances,
    # EC2
    describe_instances,
    describe_security_groups,
    describe_vpcs,
    describe_subnets,
    describe_autoscaling_groups,
    # RDS
    describe_db_instances,
    describe_db_clusters,
    describe_db_events,
    get_rds_log_file_portion,
    # DynamoDB
    describe_dynamodb_table,
    list_dynamodb_tables,
    get_dynamodb_metrics,
    # S3
    list_buckets,
    get_bucket_metadata,
    get_bucket_policy,
    get_s3_metrics,
    # SQS
    list_queues,
    get_queue_attributes,
    get_sqs_dead_letter_source_queues,
    # SNS
    list_topics,
    get_topic_attributes,
    # ELB
    describe_load_balancers,
    describe_listeners,
    describe_target_groups,
    describe_target_health,
    # API Gateway
    list_rest_apis,
    get_stages,
    get_api_gateway_metrics,
    # CloudFront
    list_distributions,
    get_distribution_config,
    # Lambda
    list_lambda_functions,
    get_function_configuration,
    get_lambda_metrics,
    # Step Functions
    list_state_machines,
    describe_state_machine,
    list_executions,
    get_execution_history,
    # Glue
    list_glue_jobs,
    get_glue_job_runs,
    get_glue_crawlers,
    # ElastiCache
    describe_cache_clusters,
    get_elasticache_metrics,
    # ECR
    list_repositories,
    describe_images,
    # KMS
    list_kms_keys,
    describe_kms_key,
    # Secrets Manager
    list_secrets,
    # IAM
    get_role,
    simulate_principal_policy,
    # ACM
    list_certificates,
    describe_certificate,
    # Route 53
    list_hosted_zones,
    list_resource_record_sets,
    # SES
    get_send_statistics,
    get_account_sending_enabled,
    # CloudTrail
    lookup_cloudtrail_events,
    get_trail_status,
    # SSM
    describe_ssm_parameters,
    get_parameters_by_path,
    # Resource Tagging
    list_tagged_resources,
]

# ── Mock mode ──────────────────────────────────────────────────────────────────
# When MOCK_AWS=true, replace each tool's underlying function with one that
# returns pre-built fixture data instead of calling boto3.
# LangChain StructuredTool stores the real callable in .func — we swap it out
# so the tool schema, name, and description are all preserved for the LLM.

from app.config import settings  # noqa: E402
from app.tools.mock_data import MOCK_RESPONSES  # noqa: E402

if settings.mock_aws:
    for _tool in ALL_TOOLS:
        _mock = MOCK_RESPONSES.get(_tool.name)
        if _mock is not None:
            _tool.func = lambda _mock=_mock, **kwargs: _mock
