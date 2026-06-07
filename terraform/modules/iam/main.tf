locals {
  name_prefix = "${var.project_name}-${var.environment}"
  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

data "aws_caller_identity" "current" {}

# ── ECS Task Role ─────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "task_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "agent_task_role" {
  name               = "${local.name_prefix}-task-role"
  assume_role_policy = data.aws_iam_policy_document.task_assume_role.json
  tags               = local.tags
}

# ── ECS Execution Role ────────────────────────────────────────────────────────

resource "aws_iam_role" "ecs_execution_role" {
  name               = "${local.name_prefix}-execution-role"
  assume_role_policy = data.aws_iam_policy_document.task_assume_role.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ── Task Role inline policy ───────────────────────────────────────────────────

data "aws_iam_policy_document" "task_policy" {
  # CloudWatch Logs — read
  statement {
    sid    = "CloudWatchLogsRead"
    effect = "Allow"
    actions = [
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:GetLogEvents",
      "logs:FilterLogEvents",
      "logs:StartQuery",
      "logs:StopQuery",
      "logs:GetQueryResults",
      "logs:GetLogGroupFields",      # needed for Logs Insights field discovery
    ]
    resources = ["*"]
  }

  # CloudWatch Metrics — read
  statement {
    sid    = "CloudWatchMetricsRead"
    effect = "Allow"
    actions = [
      "cloudwatch:GetMetricData",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:ListMetrics",
      "cloudwatch:DescribeAlarms",
      "cloudwatch:DescribeAlarmsForMetric",
      "cloudwatch:DescribeAlarmHistory",   # alarm state change history
    ]
    resources = ["*"]
  }

  # ECS — read
  statement {
    sid    = "ECSRead"
    effect = "Allow"
    actions = [
      "ecs:ListClusters",
      "ecs:DescribeClusters",
      "ecs:ListServices",
      "ecs:DescribeServices",
      "ecs:ListTasks",
      "ecs:DescribeTasks",
      "ecs:DescribeTaskDefinition",
      "ecs:ListTaskDefinitions",
      "ecs:ListContainerInstances",
      "ecs:DescribeContainerInstances",
    ]
    resources = ["*"]
  }

  # EC2 — read
  statement {
    sid    = "EC2Read"
    effect = "Allow"
    actions = [
      "ec2:DescribeInstances",
      "ec2:DescribeInstanceStatus",
      "ec2:DescribeVpcs",
      "ec2:DescribeSubnets",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DescribeLoadBalancers",
      "ec2:DescribeAvailabilityZones",
      "ec2:DescribeRegions",
      "ec2:DescribeTags",
      "ec2:DescribeVolumes",
      "ec2:DescribeImages",
      "ec2:DescribeSnapshots",
      "ec2:DescribeRouteTables",
      "ec2:DescribeInternetGateways",
      "ec2:DescribeNatGateways",
      "ec2:DescribeVpcEndpoints",
    ]
    resources = ["*"]
  }

  # Auto Scaling — read
  statement {
    sid    = "AutoScalingRead"
    effect = "Allow"
    actions = [
      "autoscaling:DescribeAutoScalingGroups",
      "autoscaling:DescribeAutoScalingInstances",
      "autoscaling:DescribeLaunchConfigurations",
      "autoscaling:DescribeScalingActivities",
      "autoscaling:DescribePolicies",
    ]
    resources = ["*"]
  }

  # RDS — read
  statement {
    sid    = "RDSRead"
    effect = "Allow"
    actions = [
      "rds:DescribeDBInstances",
      "rds:DescribeDBClusters",
      "rds:DescribeDBSubnetGroups",
      "rds:DescribeDBParameterGroups",
      "rds:DescribeDBClusterParameters",
      "rds:DescribeDBLogFiles",
      "rds:DownloadDBLogFilePortion",
      "rds:DescribeEvents",           # 🔴 required by describe_db_events tool
      "rds:ListTagsForResource",
    ]
    resources = ["*"]
  }

  # DynamoDB — read all (for triage visibility of customer tables)
  statement {
    sid    = "DynamoDBReadAll"
    effect = "Allow"
    actions = [
      "dynamodb:ListTables",
      "dynamodb:DescribeTable",
      "dynamodb:DescribeTimeToLive",
      "dynamodb:ListTagsOfResource",
      "dynamodb:DescribeLimits",
    ]
    resources = ["*"]
  }

  # DynamoDB — read/write on triage tables only
  statement {
    sid    = "DynamoDBTriageTables"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem",
    ]
    resources = [
      var.sessions_table_arn,
      "${var.sessions_table_arn}/index/*",
      var.messages_table_arn,
      "${var.messages_table_arn}/index/*",
    ]
  }

  # S3 — read
  statement {
    sid    = "S3Read"
    effect = "Allow"
    actions = [
      "s3:ListAllMyBuckets",
      "s3:GetBucketLocation",
      "s3:GetBucketVersioning",
      "s3:GetBucketLogging",
      "s3:GetBucketPolicy",
      "s3:GetBucketAcl",
      "s3:GetBucketNotification",
      "s3:GetBucketWebsite",
      "s3:GetBucketEncryption",
      "s3:GetBucketPublicAccessBlock",
      "s3:ListBucket",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:GetObjectTagging",
    ]
    resources = ["*"]
  }

  # SQS — read
  statement {
    sid    = "SQSRead"
    effect = "Allow"
    actions = [
      "sqs:ListQueues",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ListQueueTags",
      "sqs:ListDeadLetterSourceQueues",  # 🔴 required by get_sqs_dead_letter_source_queues tool
    ]
    resources = ["*"]
  }

  # SNS — read
  statement {
    sid    = "SNSRead"
    effect = "Allow"
    actions = [
      "sns:ListTopics",
      "sns:GetTopicAttributes",
      "sns:ListSubscriptions",
      "sns:ListSubscriptionsByTopic",
      "sns:ListTagsForResource",
    ]
    resources = ["*"]
  }

  # ELB — read
  statement {
    sid    = "ELBRead"
    effect = "Allow"
    actions = [
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeLoadBalancerAttributes",
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeTargetGroupAttributes",
      "elasticloadbalancing:DescribeTargetHealth",
      "elasticloadbalancing:DescribeListeners",
      "elasticloadbalancing:DescribeRules",
      "elasticloadbalancing:DescribeTags",
    ]
    resources = ["*"]
  }

  # API Gateway — GET only
  statement {
    sid    = "APIGatewayRead"
    effect = "Allow"
    actions = [
      "apigateway:GET",
    ]
    resources = ["arn:aws:apigateway:${var.aws_region}::/*"]
  }

  # CloudFront — read
  statement {
    sid    = "CloudFrontRead"
    effect = "Allow"
    actions = [
      "cloudfront:ListDistributions",
      "cloudfront:GetDistribution",
      "cloudfront:GetDistributionConfig",   # 🔴 required by get_distribution_config tool
      "cloudfront:ListInvalidations",
      "cloudfront:GetInvalidation",
    ]
    resources = ["*"]
  }

  # Lambda — read
  statement {
    sid    = "LambdaRead"
    effect = "Allow"
    actions = [
      "lambda:ListFunctions",
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:ListAliases",
      "lambda:ListVersionsByFunction",
      "lambda:ListEventSourceMappings",
      "lambda:GetPolicy",
    ]
    resources = ["*"]
  }

  # Step Functions — read
  statement {
    sid    = "StepFunctionsRead"
    effect = "Allow"
    actions = [
      "states:ListStateMachines",
      "states:DescribeStateMachine",
      "states:ListExecutions",
      "states:DescribeExecution",
      "states:GetExecutionHistory",   # 🔴 required by get_execution_history tool
    ]
    resources = ["*"]
  }

  # Glue — read
  statement {
    sid    = "GlueRead"
    effect = "Allow"
    actions = [
      "glue:ListJobs",
      "glue:GetDatabases",
      "glue:GetTables",
      "glue:GetJobs",
      "glue:GetCrawlers",
      "glue:GetCrawler",
      "glue:GetJob",
      "glue:GetJobRun",
      "glue:GetJobRuns",
    ]
    resources = ["*"]
  }

  # ElastiCache — read
  statement {
    sid    = "ElastiCacheRead"
    effect = "Allow"
    actions = [
      "elasticache:DescribeCacheClusters",
      "elasticache:DescribeReplicationGroups",
      "elasticache:DescribeCacheSubnetGroups",
      "elasticache:DescribeCacheParameters",
      "elasticache:DescribeEvents",
      "elasticache:ListTagsForResource",
    ]
    resources = ["*"]
  }

  # ECR — read
  statement {
    sid    = "ECRRead"
    effect = "Allow"
    actions = [
      "ecr:DescribeRepositories",
      "ecr:ListImages",
      "ecr:DescribeImages",
      "ecr:GetRepositoryPolicy",
      "ecr:ListTagsForResource",
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }

  # KMS — read
  statement {
    sid    = "KMSRead"
    effect = "Allow"
    actions = [
      "kms:ListKeys",
      "kms:DescribeKey",
      "kms:ListAliases",
      "kms:GetKeyPolicy",
      "kms:GetKeyRotationStatus",
    ]
    resources = ["*"]
  }

  # Secrets Manager — describe only
  statement {
    sid    = "SecretsManagerDescribe"
    effect = "Allow"
    actions = [
      "secretsmanager:ListSecrets",
      "secretsmanager:DescribeSecret",
    ]
    resources = ["*"]
  }

  # IAM — read
  statement {
    sid    = "IAMRead"
    effect = "Allow"
    actions = [
      "iam:ListRoles",
      "iam:GetRole",
      "iam:ListPolicies",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:ListAttachedRolePolicies",
      "iam:ListRolePolicies",
      "iam:GetRolePolicy",
      "iam:SimulatePrincipalPolicy",  # 🔴 required by simulate_principal_policy tool
      "iam:ListUsers",
      "iam:GetUser",
      "iam:ListGroups",
    ]
    resources = ["*"]
  }

  # ACM — read
  statement {
    sid    = "ACMRead"
    effect = "Allow"
    actions = [
      "acm:ListCertificates",
      "acm:DescribeCertificate",
      "acm:ListTagsForCertificate",
    ]
    resources = ["*"]
  }

  # Route 53 — read
  statement {
    sid    = "Route53Read"
    effect = "Allow"
    actions = [
      "route53:ListHostedZones",
      "route53:GetHostedZone",
      "route53:ListResourceRecordSets",
      "route53:ListHealthChecks",
      "route53:GetHealthCheck",
    ]
    resources = ["*"]
  }

  # SES — read
  statement {
    sid    = "SESRead"
    effect = "Allow"
    actions = [
      "ses:ListIdentities",
      "ses:GetIdentityVerificationAttributes",
      "ses:GetSendQuota",
      "ses:GetSendStatistics",
      "ses:GetAccountSendingEnabled",
      "ses:ListConfigurationSets",
    ]
    resources = ["*"]
  }

  # SES v2 — read
  statement {
    sid    = "SESv2Read"
    effect = "Allow"
    actions = [
      "ses:GetAccount",                   # sesv2 uses ses: prefix in IAM
      "ses:ListSuppressedDestinations",
    ]
    resources = ["*"]
  }

  # CloudTrail — read
  statement {
    sid    = "CloudTrailRead"
    effect = "Allow"
    actions = [
      "cloudtrail:DescribeTrails",
      "cloudtrail:GetTrailStatus",
      "cloudtrail:LookupEvents",
      "cloudtrail:ListTrails",
    ]
    resources = ["*"]
  }

  # SSM — describe + get by path (no secret values)
  statement {
    sid    = "SSMRead"
    effect = "Allow"
    actions = [
      "ssm:DescribeParameters",
      "ssm:GetParametersByPath",
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:ListTagsForResource",
    ]
    resources = ["*"]
  }

  # Resource Tagging + Resource Groups
  statement {
    sid    = "TaggingRead"
    effect = "Allow"
    actions = [
      "tag:GetResources",
      "tag:GetTagKeys",
      "tag:GetTagValues",
      "resource-groups:ListGroups",
      "resource-groups:GetGroup",
      "resource-groups:GetGroupQuery",
    ]
    resources = ["*"]
  }

  # Bedrock — invoke models
  statement {
    sid    = "BedrockInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-*",
    ]
  }
}

resource "aws_iam_role_policy" "task_policy" {
  name   = "${local.name_prefix}-task-policy"
  role   = aws_iam_role.agent_task_role.id
  policy = data.aws_iam_policy_document.task_policy.json
}
