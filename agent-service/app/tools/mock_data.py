"""
Realistic mock responses for every tool — used when MOCK_AWS=true.

Scenario: a payment-service ECS task is OOM-killing (exit code 137),
causing the ALB target group to show unhealthy targets and elevated 5xx
on the API Gateway. Useful for testing the full agent triage loop locally
without real AWS credentials.
"""

from datetime import datetime, timezone, timedelta

_NOW = datetime.now(timezone.utc)
_1H_AGO = (_NOW - timedelta(hours=1)).isoformat()
_NOW_ISO = _NOW.isoformat()


# ── CloudWatch Logs ────────────────────────────────────────────────────────────

MOCK_LIST_LOG_GROUPS = {
    "log_groups": [
        "/ecs/payment-service",
        "/ecs/user-service",
        "/ecs/api-gateway",
        "/aws/lambda/process-payments",
        "/aws/rds/cluster/prod-aurora",
    ]
}

MOCK_QUERY_CLOUDWATCH_LOGS = {
    "results": [
        {"timestamp": _1H_AGO, "message": "ERROR OutOfMemoryError: Java heap space", "logStreamName": "payment-service/app/abc123"},
        {"timestamp": _1H_AGO, "message": "WARN  Memory usage at 94% (482MB/512MB)", "logStreamName": "payment-service/app/abc123"},
        {"timestamp": _1H_AGO, "message": "ERROR Payment processing failed: connection timeout to RDS", "logStreamName": "payment-service/app/abc123"},
        {"timestamp": _1H_AGO, "message": "ERROR OutOfMemoryError: Java heap space", "logStreamName": "payment-service/app/def456"},
        {"timestamp": _1H_AGO, "message": "INFO  Container killed by OOM killer (exit 137)", "logStreamName": "payment-service/app/def456"},
    ],
    "statistics": {"recordsScanned": 15420, "recordsMatched": 5},
}

MOCK_FILTER_LOG_EVENTS = MOCK_QUERY_CLOUDWATCH_LOGS

MOCK_GET_LOG_EVENTS = {
    "events": [
        {"timestamp": _1H_AGO, "message": "INFO  Starting payment-service v2.3.1"},
        {"timestamp": _1H_AGO, "message": "WARN  Memory usage at 94% (482MB/512MB)"},
        {"timestamp": _1H_AGO, "message": "ERROR OutOfMemoryError: Java heap space"},
        {"timestamp": _1H_AGO, "message": "INFO  Container killed by OOM killer (exit 137)"},
    ]
}


# ── CloudWatch Metrics ─────────────────────────────────────────────────────────

MOCK_GET_METRIC_STATISTICS = {
    "datapoints": [
        {"Timestamp": _1H_AGO, "Average": 320.0, "Unit": "Megabytes"},
        {"Timestamp": _1H_AGO, "Average": 420.0, "Unit": "Megabytes"},
        {"Timestamp": _NOW_ISO, "Average": 498.0, "Unit": "Megabytes"},
    ]
}

MOCK_LIST_METRICS = {
    "metrics": [
        {"Namespace": "AWS/ECS", "MetricName": "MemoryUtilization", "Dimensions": [{"Name": "ServiceName", "Value": "payment-service"}]},
        {"Namespace": "AWS/ECS", "MetricName": "CPUUtilization",    "Dimensions": [{"Name": "ServiceName", "Value": "payment-service"}]},
        {"Namespace": "AWS/ApplicationELB", "MetricName": "HTTPCode_Target_5XX_Count", "Dimensions": []},
    ]
}

MOCK_DESCRIBE_ALARMS = {
    "alarms": [
        {
            "AlarmName": "payment-service-memory-high",
            "StateValue": "ALARM",
            "StateReason": "Threshold Crossed: 1 datapoint (98.0) was greater than or equal to the threshold (90.0).",
            "MetricName": "MemoryUtilization",
            "Threshold": 90.0,
            "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        },
        {
            "AlarmName": "api-gateway-5xx-rate",
            "StateValue": "ALARM",
            "StateReason": "Threshold Crossed: 5xx error rate exceeded 5%.",
            "MetricName": "5XXError",
            "Threshold": 5.0,
            "ComparisonOperator": "GreaterThanThreshold",
        },
    ]
}


# ── ECS ────────────────────────────────────────────────────────────────────────

MOCK_LIST_ECS_CLUSTERS = {
    "clusters": ["arn:aws:ecs:us-east-1:123456789012:cluster/prod-cluster"]
}

MOCK_DESCRIBE_ECS_SERVICES = {
    "services": [
        {
            "serviceName": "payment-service",
            "clusterArn": "arn:aws:ecs:us-east-1:123456789012:cluster/prod-cluster",
            "status": "ACTIVE",
            "desiredCount": 2,
            "runningCount": 1,
            "pendingCount": 1,
            "deployments": [{"status": "PRIMARY", "desiredCount": 2, "runningCount": 1}],
            "events": [
                {"createdAt": _NOW_ISO, "message": "(service payment-service) has started 1 tasks: (task abc123)."},
                {"createdAt": _1H_AGO,  "message": "(service payment-service) has stopped 1 running tasks: (task def456) with exit code 137."},
            ],
        }
    ]
}

MOCK_DESCRIBE_ECS_TASKS = {
    "tasks": [
        {
            "taskArn": "arn:aws:ecs:us-east-1:123456789012:task/prod-cluster/abc123",
            "lastStatus": "RUNNING",
            "desiredStatus": "RUNNING",
            "cpu": "512",
            "memory": "512",
            "containers": [{"name": "payment-service", "lastStatus": "RUNNING", "exitCode": None}],
        },
        {
            "taskArn": "arn:aws:ecs:us-east-1:123456789012:task/prod-cluster/def456",
            "lastStatus": "STOPPED",
            "desiredStatus": "STOPPED",
            "stoppedReason": "Essential container in task exited",
            "cpu": "512",
            "memory": "512",
            "containers": [{"name": "payment-service", "lastStatus": "STOPPED", "exitCode": 137}],
        },
    ]
}

MOCK_GET_TASK_STOPPED_REASON = {
    "stopped_reason": "Essential container in task exited",
    "container_exit_codes": {"payment-service": 137},
    "container_reasons": {"payment-service": "OOMKilled: container exceeded memory limit of 512MB"},
}

MOCK_DESCRIBE_ECS_CONTAINER_INSTANCES = {"instances": []}


# ── EC2 ────────────────────────────────────────────────────────────────────────

MOCK_DESCRIBE_INSTANCES = {
    "instances": [
        {
            "InstanceId": "i-0abc123def456789",
            "InstanceType": "t3.medium",
            "State": {"Name": "running"},
            "PrivateIpAddress": "10.0.1.50",
            "Tags": [{"Key": "Name", "Value": "prod-bastion"}, {"Key": "Environment", "Value": "prod"}],
        }
    ]
}

MOCK_DESCRIBE_SECURITY_GROUPS = {
    "security_groups": [
        {
            "GroupId": "sg-0abc123",
            "GroupName": "payment-service-sg",
            "Description": "Payment service ECS tasks",
            "IpPermissions": [{"IpProtocol": "tcp", "FromPort": 8080, "ToPort": 8080, "IpRanges": [{"CidrIp": "10.0.0.0/8"}]}],
            "IpPermissionsEgress": [{"IpProtocol": "-1", "IpRanges": [{"CidrIp": "0.0.0.0/0"}]}],
        }
    ]
}

MOCK_DESCRIBE_VPCS = {
    "vpcs": [
        {"VpcId": "vpc-0abc123", "CidrBlock": "10.0.0.0/16", "State": "available",
         "Tags": [{"Key": "Name", "Value": "prod-vpc"}]}
    ]
}

MOCK_DESCRIBE_SUBNETS = {
    "subnets": [
        {"SubnetId": "subnet-0aaa", "VpcId": "vpc-0abc123", "CidrBlock": "10.0.1.0/24",
         "AvailabilityZone": "us-east-1a", "AvailableIpAddressCount": 200, "Tags": [{"Key": "Name", "Value": "private-1a"}]},
        {"SubnetId": "subnet-0bbb", "VpcId": "vpc-0abc123", "CidrBlock": "10.0.2.0/24",
         "AvailabilityZone": "us-east-1b", "AvailableIpAddressCount": 198, "Tags": [{"Key": "Name", "Value": "private-1b"}]},
    ]
}

MOCK_DESCRIBE_AUTOSCALING_GROUPS = {"groups": []}


# ── RDS ────────────────────────────────────────────────────────────────────────

MOCK_DESCRIBE_DB_INSTANCES = {
    "instances": [
        {
            "DBInstanceIdentifier": "prod-postgres-1",
            "DBInstanceClass": "db.t3.medium",
            "Engine": "postgres",
            "DBInstanceStatus": "available",
            "Endpoint": {"Address": "prod-postgres-1.xyz.us-east-1.rds.amazonaws.com", "Port": 5432},
            "MultiAZ": True,
        }
    ]
}

MOCK_DESCRIBE_DB_CLUSTERS = {"clusters": []}
MOCK_DESCRIBE_DB_EVENTS = {"events": []}
MOCK_GET_RDS_LOG_FILE_PORTION = {"log_data": "2026-06-07 02:10:00 UTC [123]: LOG:  checkpoint starting: time\n2026-06-07 02:10:01 UTC [123]: LOG:  checkpoint complete"}


# ── DynamoDB ───────────────────────────────────────────────────────────────────

MOCK_LIST_DYNAMODB_TABLES = {"table_names": ["orders", "users", "sessions"]}
MOCK_DESCRIBE_DYNAMODB_TABLE = {
    "table": {"TableName": "orders", "TableStatus": "ACTIVE", "ItemCount": 142000,
               "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"}}
}
MOCK_GET_DYNAMODB_METRICS = {
    "metrics": {"ConsumedReadCapacityUnits": 45.2, "ConsumedWriteCapacityUnits": 12.1,
                 "ThrottledRequests": 0, "SystemErrors": 0}
}


# ── S3 ─────────────────────────────────────────────────────────────────────────

MOCK_LIST_BUCKETS = {
    "buckets": [
        {"Name": "prod-assets", "CreationDate": "2024-01-01"},
        {"Name": "prod-logs",   "CreationDate": "2024-01-01"},
    ]
}
MOCK_GET_BUCKET_METADATA = {"metadata": {"versioning": "Enabled", "encryption": "AES256", "publicAccessBlocked": True}}
MOCK_GET_BUCKET_POLICY = {"policy": None, "public_access_block": {"BlockPublicAcls": True}}
MOCK_GET_S3_METRICS = {"metrics": {"BucketSizeBytes": 5368709120, "NumberOfObjects": 12000, "4xxErrors": 0, "5xxErrors": 0}}


# ── SQS ────────────────────────────────────────────────────────────────────────

MOCK_LIST_QUEUES = {"queue_urls": ["https://sqs.us-east-1.amazonaws.com/123456789012/payment-events"]}
MOCK_GET_QUEUE_ATTRIBUTES = {
    "attributes": {
        "ApproximateNumberOfMessages": "0",
        "ApproximateNumberOfMessagesNotVisible": "3",
        "ApproximateAgeOfOldestMessage": "45",
        "VisibilityTimeout": "30",
        "MessageRetentionPeriod": "345600",
    }
}
MOCK_GET_SQS_DLQ_SOURCES = {"source_queues": []}


# ── SNS ────────────────────────────────────────────────────────────────────────

MOCK_LIST_TOPICS = {"topics": [{"TopicArn": "arn:aws:sns:us-east-1:123456789012:payment-alerts", "Name": "payment-alerts"}]}
MOCK_GET_TOPIC_ATTRIBUTES = {"attributes": {"SubscriptionsConfirmed": "2", "SubscriptionsPending": "0"}}


# ── ALB ────────────────────────────────────────────────────────────────────────

MOCK_DESCRIBE_LOAD_BALANCERS = {
    "load_balancers": [
        {"LoadBalancerName": "prod-alb", "DNSName": "prod-alb.us-east-1.elb.amazonaws.com",
         "State": {"Code": "active"}, "Type": "application", "Scheme": "internet-facing"}
    ]
}
MOCK_DESCRIBE_LISTENERS = {
    "listeners": [{"ListenerArn": "arn:aws:elasticloadbalancing:...", "Port": 443, "Protocol": "HTTPS"}]
}
MOCK_DESCRIBE_TARGET_GROUPS = {
    "target_groups": [
        {"TargetGroupName": "payment-service-tg", "Port": 8080, "Protocol": "HTTP",
         "HealthCheckPath": "/health", "HealthyThresholdCount": 2, "UnhealthyThresholdCount": 3}
    ]
}
MOCK_DESCRIBE_TARGET_HEALTH = {
    "targets": [
        {"Target": {"Id": "10.0.1.101", "Port": 8080}, "TargetHealth": {"State": "healthy"}},
        {"Target": {"Id": "10.0.2.102", "Port": 8080}, "TargetHealth": {"State": "unhealthy",
         "Reason": "Target.FailedHealthChecks", "Description": "Health checks failed"}},
    ]
}


# ── API Gateway ────────────────────────────────────────────────────────────────

MOCK_LIST_REST_APIS = {
    "apis": [{"id": "abc123xyz", "name": "prod-api", "endpointType": "REGIONAL", "createdDate": "2024-01-01"}]
}
MOCK_GET_STAGES = {
    "stages": [{"stageName": "prod", "deploymentId": "xyz", "throttlingBurstLimit": 5000}]
}
MOCK_GET_API_GATEWAY_METRICS = {
    "metrics": {"Count": 18420, "4XXError": 142, "5XXError": 893,
                 "Latency_p50": 245, "Latency_p99": 4210, "IntegrationLatency_p99": 4100}
}


# ── CloudFront ─────────────────────────────────────────────────────────────────

MOCK_LIST_DISTRIBUTIONS = {
    "distributions": [{"Id": "ABCDEF123", "DomainName": "d1234.cloudfront.net", "Status": "Deployed",
                        "Aliases": ["app.example.com"]}]
}
MOCK_GET_DISTRIBUTION_CONFIG = {
    "config": {"Origins": [{"DomainName": "prod-alb.us-east-1.elb.amazonaws.com"}],
               "HttpVersion": "http2", "PriceClass": "PriceClass_100"}
}


# ── Lambda ─────────────────────────────────────────────────────────────────────

MOCK_LIST_LAMBDA_FUNCTIONS = {
    "functions": [
        {"FunctionName": "process-payments", "Runtime": "python3.12", "MemorySize": 512,
         "Timeout": 30, "LastModified": "2026-05-01T00:00:00.000+0000"}
    ]
}
MOCK_GET_FUNCTION_CONFIGURATION = {
    "config": {"FunctionName": "process-payments", "Runtime": "python3.12", "Handler": "handler.main",
               "MemorySize": 512, "Timeout": 30, "Environment": {"Variables": {"DB_HOST": "[REDACTED]"}}}
}
MOCK_GET_LAMBDA_METRICS = {
    "metrics": {"Invocations": 4201, "Errors": 12, "Throttles": 0,
                 "Duration_p50": 180, "Duration_p99": 2800, "ConcurrentExecutions": 8}
}


# ── Step Functions ─────────────────────────────────────────────────────────────

MOCK_LIST_STATE_MACHINES = {"state_machines": []}
MOCK_DESCRIBE_STATE_MACHINE = {"error": "No state machines found"}
MOCK_LIST_EXECUTIONS = {"executions": []}
MOCK_GET_EXECUTION_HISTORY = {"events": []}


# ── Glue ───────────────────────────────────────────────────────────────────────

MOCK_LIST_GLUE_JOBS = {"jobs": []}
MOCK_GET_GLUE_JOB_RUNS = {"runs": []}
MOCK_GET_GLUE_CRAWLERS = {"crawlers": []}


# ── ElastiCache ────────────────────────────────────────────────────────────────

MOCK_DESCRIBE_CACHE_CLUSTERS = {
    "clusters": [
        {"CacheClusterId": "prod-redis", "Engine": "redis", "EngineVersion": "7.1.0",
         "CacheClusterStatus": "available", "CacheNodeType": "cache.t3.medium", "NumCacheNodes": 1}
    ]
}
MOCK_GET_ELASTICACHE_METRICS = {
    "metrics": {"CurrConnections": 142, "Evictions": 0, "CacheHits": 98420,
                 "CacheMisses": 1820, "CacheHitRate": 0.982, "FreeableMemory": 512000000}
}


# ── ECR ────────────────────────────────────────────────────────────────────────

MOCK_LIST_REPOSITORIES = {
    "repositories": [
        {"repositoryName": "payment-service", "repositoryUri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/payment-service",
         "imageTagMutability": "MUTABLE"}
    ]
}
MOCK_DESCRIBE_IMAGES = {
    "images": [
        {"imageTags": ["latest", "v2.3.1"], "imagePushedAt": "2026-06-01T00:00:00+00:00",
         "imageSizeInBytes": 184320000}
    ]
}


# ── KMS ────────────────────────────────────────────────────────────────────────

MOCK_LIST_KMS_KEYS = {"keys": [{"KeyId": "abc-123", "KeyArn": "arn:aws:kms:us-east-1:123456789012:key/abc-123"}]}
MOCK_DESCRIBE_KMS_KEY = {
    "metadata": {"KeyId": "abc-123", "Description": "prod-data-key", "KeyState": "Enabled",
                  "KeyUsage": "ENCRYPT_DECRYPT", "RotationEnabled": True}
}


# ── Secrets Manager ────────────────────────────────────────────────────────────

MOCK_LIST_SECRETS = {
    "secrets": [
        {"Name": "/prod/payment-service/db-password", "ARN": "arn:aws:secretsmanager:...",
         "RotationEnabled": True, "LastRotatedDate": "2026-05-01T00:00:00+00:00"}
    ]
}


# ── IAM ────────────────────────────────────────────────────────────────────────

MOCK_GET_ROLE = {
    "role": {"RoleName": "payment-service-task-role",
              "AttachedPolicies": ["PaymentServiceReadOnly"],
              "LastUsedDate": _NOW_ISO}
}
MOCK_SIMULATE_PRINCIPAL_POLICY = {
    "results": [{"EvalActionName": "s3:GetObject", "EvalDecision": "allowed"}]
}


# ── ACM ────────────────────────────────────────────────────────────────────────

MOCK_LIST_CERTIFICATES = {
    "certificates": [
        {"CertificateArn": "arn:aws:acm:us-east-1:123456789012:certificate/abc",
         "DomainName": "*.example.com", "Status": "ISSUED"}
    ]
}
MOCK_DESCRIBE_CERTIFICATE = {
    "certificate": {"DomainName": "*.example.com", "Status": "ISSUED",
                     "NotAfter": "2027-06-01T00:00:00+00:00", "InUseBy": ["prod-alb"]}
}


# ── Route 53 ───────────────────────────────────────────────────────────────────

MOCK_LIST_HOSTED_ZONES = {
    "zones": [{"Id": "/hostedzone/ABC123", "Name": "example.com.", "Type": "public", "RecordCount": 12}]
}
MOCK_LIST_RESOURCE_RECORD_SETS = {
    "record_sets": [
        {"Name": "app.example.com.", "Type": "A", "AliasTarget": "d1234.cloudfront.net"},
        {"Name": "api.example.com.", "Type": "CNAME", "TTL": 300, "Values": ["prod-alb.us-east-1.elb.amazonaws.com"]},
    ]
}


# ── SES ────────────────────────────────────────────────────────────────────────

MOCK_GET_SEND_STATISTICS = {
    "data_points": [
        {"Timestamp": _1H_AGO, "DeliveryAttempts": 420, "Bounces": 2, "Complaints": 0, "Rejects": 0}
    ]
}
MOCK_GET_ACCOUNT_SENDING_ENABLED = {
    "enabled": True,
    "sending_quota": {"Max24HourSend": 50000, "MaxSendRate": 14.0, "SentLast24Hours": 3820},
}


# ── CloudTrail ─────────────────────────────────────────────────────────────────

MOCK_LOOKUP_CLOUDTRAIL_EVENTS = {
    "events": [
        {"EventTime": _1H_AGO, "EventName": "UpdateService", "Username": "deploy-bot",
         "SourceIPAddress": "10.0.1.10",
         "RequestParameters": {"service": "payment-service", "desiredCount": 2, "taskDefinition": "payment-service:42"}},
    ]
}
MOCK_GET_TRAIL_STATUS = {
    "status": {"IsLogging": True, "LatestDeliveryTime": _1H_AGO, "LatestDeliveryError": None}
}


# ── SSM ────────────────────────────────────────────────────────────────────────

MOCK_DESCRIBE_SSM_PARAMETERS = {
    "parameters": [
        {"Name": "/prod/payment-service/log-level", "Type": "String", "LastModifiedDate": _1H_AGO},
        {"Name": "/prod/payment-service/db-url",    "Type": "SecureString", "LastModifiedDate": _1H_AGO},
    ]
}
MOCK_GET_PARAMETERS_BY_PATH = {
    "parameters": [
        {"Name": "/prod/payment-service/log-level", "Type": "String", "Value": "INFO"},
        {"Name": "/prod/payment-service/db-url",    "Type": "SecureString", "Value": "[REDACTED]"},
    ]
}


# ── Resource Tagging ───────────────────────────────────────────────────────────

MOCK_LIST_TAGGED_RESOURCES = {
    "resources": [
        {"ResourceARN": "arn:aws:ecs:us-east-1:123456789012:service/prod-cluster/payment-service",
         "ResourceType": "ecs:service", "Tags": [{"Key": "Environment", "Value": "prod"}]},
        {"ResourceARN": "arn:aws:rds:us-east-1:123456789012:db:prod-postgres-1",
         "ResourceType": "rds:db",     "Tags": [{"Key": "Environment", "Value": "prod"}]},
    ]
}


# ── Lookup table: tool function name → mock response ──────────────────────────

MOCK_RESPONSES: dict = {
    "list_log_groups":                  MOCK_LIST_LOG_GROUPS,
    "query_cloudwatch_logs":            MOCK_QUERY_CLOUDWATCH_LOGS,
    "filter_log_events":                MOCK_FILTER_LOG_EVENTS,
    "get_log_events":                   MOCK_GET_LOG_EVENTS,
    "get_metric_statistics":            MOCK_GET_METRIC_STATISTICS,
    "list_metrics":                     MOCK_LIST_METRICS,
    "describe_alarms":                  MOCK_DESCRIBE_ALARMS,
    "list_ecs_clusters":                MOCK_LIST_ECS_CLUSTERS,
    "describe_ecs_services":            MOCK_DESCRIBE_ECS_SERVICES,
    "describe_ecs_tasks":               MOCK_DESCRIBE_ECS_TASKS,
    "get_task_stopped_reason":          MOCK_GET_TASK_STOPPED_REASON,
    "describe_ecs_container_instances": MOCK_DESCRIBE_ECS_CONTAINER_INSTANCES,
    "describe_instances":               MOCK_DESCRIBE_INSTANCES,
    "describe_security_groups":         MOCK_DESCRIBE_SECURITY_GROUPS,
    "describe_vpcs":                    MOCK_DESCRIBE_VPCS,
    "describe_subnets":                 MOCK_DESCRIBE_SUBNETS,
    "describe_autoscaling_groups":      MOCK_DESCRIBE_AUTOSCALING_GROUPS,
    "describe_db_instances":            MOCK_DESCRIBE_DB_INSTANCES,
    "describe_db_clusters":             MOCK_DESCRIBE_DB_CLUSTERS,
    "describe_db_events":               MOCK_DESCRIBE_DB_EVENTS,
    "get_rds_log_file_portion":         MOCK_GET_RDS_LOG_FILE_PORTION,
    "list_dynamodb_tables":             MOCK_LIST_DYNAMODB_TABLES,
    "describe_dynamodb_table":          MOCK_DESCRIBE_DYNAMODB_TABLE,
    "get_dynamodb_metrics":             MOCK_GET_DYNAMODB_METRICS,
    "list_buckets":                     MOCK_LIST_BUCKETS,
    "get_bucket_metadata":              MOCK_GET_BUCKET_METADATA,
    "get_bucket_policy":                MOCK_GET_BUCKET_POLICY,
    "get_s3_metrics":                   MOCK_GET_S3_METRICS,
    "list_queues":                      MOCK_LIST_QUEUES,
    "get_queue_attributes":             MOCK_GET_QUEUE_ATTRIBUTES,
    "get_sqs_dead_letter_source_queues":MOCK_GET_SQS_DLQ_SOURCES,
    "list_topics":                      MOCK_LIST_TOPICS,
    "get_topic_attributes":             MOCK_GET_TOPIC_ATTRIBUTES,
    "describe_load_balancers":          MOCK_DESCRIBE_LOAD_BALANCERS,
    "describe_listeners":               MOCK_DESCRIBE_LISTENERS,
    "describe_target_groups":           MOCK_DESCRIBE_TARGET_GROUPS,
    "describe_target_health":           MOCK_DESCRIBE_TARGET_HEALTH,
    "list_rest_apis":                   MOCK_LIST_REST_APIS,
    "get_stages":                       MOCK_GET_STAGES,
    "get_api_gateway_metrics":          MOCK_GET_API_GATEWAY_METRICS,
    "list_distributions":               MOCK_LIST_DISTRIBUTIONS,
    "get_distribution_config":          MOCK_GET_DISTRIBUTION_CONFIG,
    "list_lambda_functions":            MOCK_LIST_LAMBDA_FUNCTIONS,
    "get_function_configuration":       MOCK_GET_FUNCTION_CONFIGURATION,
    "get_lambda_metrics":               MOCK_GET_LAMBDA_METRICS,
    "list_state_machines":              MOCK_LIST_STATE_MACHINES,
    "describe_state_machine":           MOCK_DESCRIBE_STATE_MACHINE,
    "list_executions":                  MOCK_LIST_EXECUTIONS,
    "get_execution_history":            MOCK_GET_EXECUTION_HISTORY,
    "list_glue_jobs":                   MOCK_LIST_GLUE_JOBS,
    "get_glue_job_runs":                MOCK_GET_GLUE_JOB_RUNS,
    "get_glue_crawlers":                MOCK_GET_GLUE_CRAWLERS,
    "describe_cache_clusters":          MOCK_DESCRIBE_CACHE_CLUSTERS,
    "get_elasticache_metrics":          MOCK_GET_ELASTICACHE_METRICS,
    "list_repositories":                MOCK_LIST_REPOSITORIES,
    "describe_images":                  MOCK_DESCRIBE_IMAGES,
    "list_kms_keys":                    MOCK_LIST_KMS_KEYS,
    "describe_kms_key":                 MOCK_DESCRIBE_KMS_KEY,
    "list_secrets":                     MOCK_LIST_SECRETS,
    "get_role":                         MOCK_GET_ROLE,
    "simulate_principal_policy":        MOCK_SIMULATE_PRINCIPAL_POLICY,
    "list_certificates":                MOCK_LIST_CERTIFICATES,
    "describe_certificate":             MOCK_DESCRIBE_CERTIFICATE,
    "list_hosted_zones":                MOCK_LIST_HOSTED_ZONES,
    "list_resource_record_sets":        MOCK_LIST_RESOURCE_RECORD_SETS,
    "get_send_statistics":              MOCK_GET_SEND_STATISTICS,
    "get_account_sending_enabled":      MOCK_GET_ACCOUNT_SENDING_ENABLED,
    "lookup_cloudtrail_events":         MOCK_LOOKUP_CLOUDTRAIL_EVENTS,
    "get_trail_status":                 MOCK_GET_TRAIL_STATUS,
    "describe_ssm_parameters":          MOCK_DESCRIBE_SSM_PARAMETERS,
    "get_parameters_by_path":           MOCK_GET_PARAMETERS_BY_PATH,
    "list_tagged_resources":            MOCK_LIST_TAGGED_RESOURCES,
}
