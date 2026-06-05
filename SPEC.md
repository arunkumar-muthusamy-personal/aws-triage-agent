# AWS Triage Agent — Application Specification

**Version:** 1.0.0  
**Status:** Design / Pre-Build  
**Owner:** Infrastructure / Platform Team  

---

## 1. Overview

### 1.1 Problem Statement

Debugging production incidents in AWS environments requires context-switching across multiple consoles: CloudWatch Logs Insights, the AWS Console, CloudTrail, EC2/ECS dashboards, and RDS metrics. This is slow, error-prone, and requires deep AWS expertise from every on-call engineer.

### 1.2 Solution

A conversational AI triage agent that acts as an intelligent on-call assistant. Engineers describe a problem in plain English; the agent autonomously queries CloudWatch Logs, calls AWS read APIs, correlates signals across services, and produces a structured diagnosis with recommended remediations — all within a browser-based chat interface.

### 1.3 Guiding Principles

- **Read-only by design.** The agent's IAM role has zero write/mutate permissions. It can observe everything, change nothing.
- **Agentic loop.** The agent runs tool-call cycles until it fully resolves (or explicitly cannot resolve) the user's intent — no single-shot responses.
- **Clarification-first.** When intent is ambiguous, the agent asks targeted clarifying questions before issuing any AWS API calls.
- **Reproducible infrastructure.** Everything deployable via Terraform; no click-ops.
- **Audit trail.** Every tool invocation and its raw output are stored, accessible, and surfaced in the UI.

---

## 2. Architecture

### 2.1 High-Level Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  User Browser                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Chat UI  (React SPA, served via CloudFront + S3)        │  │
│  └────────────────────┬─────────────────────────────────────┘  │
└───────────────────────│─────────────────────────────────────────┘
                        │ HTTPS / WebSocket (API Gateway)
┌───────────────────────▼─────────────────────────────────────────┐
│  AWS ECS Fargate Cluster                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Triage Agent Service  (FastAPI + LangGraph)             │  │
│  │                                                          │  │
│  │  ┌────────────────┐   ┌──────────────────────────────┐  │  │
│  │  │  Conversation  │   │  Agent Executor (LangGraph)  │  │  │
│  │  │  Manager       │   │                              │  │  │
│  │  │  (DynamoDB)    │◄──►  ┌──────────────────────┐   │  │  │
│  │  └────────────────┘   │  │  Tool Registry       │   │  │  │
│  │                       │  │  - CW Logs Insights  │   │  │  │
│  │                       │  │  - CW Metrics        │   │  │  │
│  │                       │  │  - ECS Describe      │   │  │  │
│  │                       │  │  - EC2 Describe      │   │  │  │
│  │                       │  │  - RDS Describe      │   │  │  │
│  │                       │  │  - ELB Describe      │   │  │  │
│  │                       │  │  - Lambda Describe   │   │  │  │
│  │                       │  │  - CloudTrail Events │   │  │  │
│  │                       │  │  - SSM Get Parameter │   │  │  │
│  │                       │  │  - SQS Attributes    │   │  │  │
│  │                       │  └──────────────────────┘   │  │  │
│  │                       └──────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
  AWS Bedrock                    AWS Service APIs
  (Claude claude-sonnet-4-20250514)      (boto3, read-only IAM role)
```

### 2.2 Component Breakdown

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Chat UI | React + TypeScript + Tailwind | Browser interface for triage conversations |
| Static Hosting | S3 + CloudFront | Serve the SPA globally |
| API Layer | API Gateway (HTTP API + WebSocket) | Route chat messages; stream agent responses |
| Agent Service | FastAPI + LangGraph + Python | Core agentic loop + tool execution |
| LLM | AWS Bedrock (Claude claude-sonnet-4-20250514) | Reasoning, tool-call orchestration, diagnosis |
| Conversation State | DynamoDB | Persist session history, tool call logs |
| Infrastructure | Terraform | All AWS resources defined as code |
| Container Registry | ECR | Agent Docker image |
| Secrets | AWS Secrets Manager | API keys, config (if any) |
| Observability | CloudWatch Logs + X-Ray | Agent's own telemetry |

---

## 3. Agent Design

### 3.1 Agent Framework: LangGraph

LangGraph is chosen because:
- Native support for **cyclic graphs** (the agent loop with tool calls)
- First-class **streaming** support — tokens and tool events stream back to the UI
- Built-in **checkpointing** compatible with DynamoDB (conversation memory)
- Tool-calling with AWS Bedrock via LangChain's `ChatBedrockConverse`

### 3.2 Agent State Machine

```
         ┌──────────────┐
         │   START       │
         └──────┬───────┘
                │  user message
                ▼
    ┌───────────────────────┐
    │  INTENT CLASSIFIER    │◄─────────────┐
    │  (LLM Node)           │              │
    └─────────┬─────────────┘              │
              │                            │
      ┌───────▼──────────┐                 │
      │  Ambiguous?      │                 │
      │  YES → CLARIFY   │─── clarification│
      │  NO  → PLAN      │    sent to user │
      └───────┬──────────┘                 │
              │                            │
    ┌─────────▼─────────────┐              │
    │  PLAN (LLM Node)      │              │
    │  Decide which tools   │              │
    │  to call and in what  │              │
    │  sequence             │              │
    └─────────┬─────────────┘              │
              │                            │
    ┌─────────▼─────────────┐              │
    │  TOOL EXECUTION Node  │              │
    │  Execute tool(s)      │              │
    │  Log inputs + outputs │              │
    └─────────┬─────────────┘              │
              │                            │
    ┌─────────▼─────────────┐              │
    │  SYNTHESIZE (LLM Node)│              │
    │  Analyze results      │              │
    │  Sufficient info?     │              │
    │  YES → DIAGNOSE       │              │
    │  NO  → loop back ─────┼─────────────┘
    └─────────┬─────────────┘
              │
    ┌─────────▼─────────────┐
    │  DIAGNOSE + REMEDIATE │
    │  (LLM Node)           │
    │  Structured output:   │
    │  - Root cause         │
    │  - Evidence           │
    │  - Recommended fixes  │
    │  - Terraform snippets │
    │    if applicable      │
    └─────────┬─────────────┘
              │
           ┌──▼───┐
           │  END  │
           └───────┘
```

### 3.3 Clarification Logic

Before any tool is invoked, the agent evaluates:

1. **Application scope** — which app/service is affected? If the account has 20 services and user says "the API is down", agent asks which API.
2. **Time window** — "last hour", "since this morning", specific timestamp?
3. **Environment** — prod vs staging (if multi-env)?
4. **Symptom type** — error rate spike, latency increase, task failure, deployment issue, cost anomaly?

The agent will ask at most **2 rounds of clarifying questions** before proceeding with best-effort assumptions (stated explicitly).

### 3.4 Agentic Loop Exit Conditions

The loop terminates when any of:
- Agent produces a `DIAGNOSE` node output with structured findings
- Max iterations reached (configurable, default: **15 tool calls**)
- A tool call returns a hard error that cannot be resolved (e.g. log group doesn't exist)
- User sends a new message mid-loop (resets intent)

### 3.5 System Prompt Design

```
You are an expert AWS infrastructure triage agent. Your job is to diagnose
production issues in AWS environments by querying CloudWatch Logs, CloudWatch
Metrics, and AWS service APIs.

You operate with READ-ONLY access. You can observe infrastructure state but
cannot modify, create, or delete any resource.

BEHAVIOR RULES:
1. If the user's request is ambiguous, ask ONE focused clarifying question before
   proceeding. Maximum 2 rounds of clarification.
2. Always state your investigation plan before executing tools.
3. Cite specific log lines, metric data points, or API responses as evidence.
4. When recommending fixes, be explicit: show the exact config change, Terraform
   snippet, or AWS Console action required.
5. If you cannot find a root cause, say so clearly and explain what additional
   access or information would be required.
6. Do not hallucinate log data. Only reference data actually returned by tools.

RESPONSE FORMAT for final diagnosis:
- **Root Cause**: [one-sentence summary]
- **Evidence**: [bullet list of specific findings with timestamps]
- **Recommended Fix**: [actionable steps, code/config snippets where relevant]
- **Prevention**: [optional: how to prevent recurrence]
```

---

## 4. Tool Registry

Each tool is a Python function wrapped as a LangChain `@tool`. All tools are **read-only**. Tools are grouped by AWS service; the source file mapping is shown in Section 8.

**Coverage summary (24 AWS services → 55 tools):**

| # | Service | Tools | File |
|---|---------|-------|------|
| 1 | CloudWatch Logs | 4 | `cloudwatch_logs.py` |
| 2 | CloudWatch Metrics & Alarms | 3 | `cloudwatch_metrics.py` |
| 3 | ECS (Fargate + EC2 launch type) | 5 | `ecs.py` |
| 4 | EC2 | 4 | `ec2.py` |
| 5 | RDS / Aurora | 4 | `rds.py` |
| 6 | DynamoDB | 3 | `dynamodb.py` |
| 7 | S3 | 4 | `s3.py` |
| 8 | SQS | 3 | `sqs.py` |
| 9 | SNS | 2 | `sns.py` |
| 10 | ALB / NLB | 4 | `elb.py` |
| 11 | API Gateway | 3 | `apigw.py` |
| 12 | CloudFront | 2 | `cloudfront.py` |
| 13 | Lambda | 3 | `lambda_.py` |
| 14 | Step Functions | 3 | `stepfunctions.py` |
| 15 | AWS Glue | 3 | `glue.py` |
| 16 | ElastiCache | 2 | `elasticache.py` |
| 17 | ECR | 2 | `ecr.py` |
| 18 | KMS (Customer Managed) | 2 | `kms.py` |
| 19 | Secrets Manager | 1 | `secretsmanager.py` |
| 20 | IAM | 2 | `iam.py` |
| 21 | ACM | 2 | `acm.py` |
| 22 | Route 53 | 2 | `route53.py` |
| 23 | SES | 2 | `ses.py` |
| 24 | CloudTrail | 2 | `cloudtrail.py` |
| 25 | Resource Tagging (discovery) | 1 | `tagging.py` |

---

### 4.1 CloudWatch Logs Tools

#### `query_cloudwatch_logs`
```python
Input:
  log_group_name: str          # e.g. /ecs/my-service
  query: str                   # CloudWatch Logs Insights query syntax
  start_time: datetime
  end_time: datetime
  limit: int = 100
Output:
  results: list[dict]
  statistics: QueryStatistics  # records scanned, records matched
```

#### `list_log_groups`
```python
Input:
  prefix: str = None           # e.g. /ecs/, /aws/lambda/
Output:
  log_groups: list[str]
```

#### `get_log_events`
```python
Input:
  log_group_name: str
  log_stream_name: str
  start_time: datetime = None
  end_time: datetime = None
  limit: int = 100
Output:
  events: list[LogEvent]
```

#### `filter_log_events`
```python
Input:
  log_group_name: str
  filter_pattern: str          # CloudWatch filter syntax e.g. "ERROR"
  start_time: datetime
  end_time: datetime
  limit: int = 100
Output:
  events: list[FilteredLogEvent]
```

---

### 4.2 CloudWatch Metrics & Alarms Tools

#### `get_metric_statistics`
```python
Input:
  namespace: str               # e.g. AWS/ECS, AWS/RDS, AWS/SQS
  metric_name: str
  dimensions: list[Dimension]
  start_time: datetime
  end_time: datetime
  period: int                  # seconds
  statistics: list[str]        # Average, Sum, Maximum, Minimum, SampleCount
Output:
  datapoints: list[Datapoint]
```

#### `list_metrics`
```python
Input:
  namespace: str = None
  dimensions: list[Dimension] = None
Output:
  metrics: list[MetricSummary]
```

#### `describe_alarms`
```python
Input:
  alarm_name_prefix: str = None
  state_value: str = None      # OK | ALARM | INSUFFICIENT_DATA
Output:
  alarms: list[AlarmDetail]    # threshold, comparison, state reason, history
```

---

### 4.3 ECS Tools
Covers both **Fargate** and **EC2 launch type** clusters.

#### `list_ecs_clusters`
```python
Output:
  clusters: list[str]          # cluster ARNs
```

#### `describe_ecs_services`
```python
Input:
  cluster: str
  services: list[str]
Output:
  services: list[ServiceDetail]
  # deployments, running/desired/pending counts, events (last 100), capacity provider
```

#### `describe_ecs_tasks`
```python
Input:
  cluster: str
  task_ids: list[str] = None
  family: str = None
  desired_status: str = None   # RUNNING | STOPPED
Output:
  tasks: list[TaskDetail]      # launch type, CPU/memory, container statuses
```

#### `get_task_stopped_reason`
```python
Input:
  cluster: str
  task_id: str
Output:
  stopped_reason: str
  container_exit_codes: dict[str, int]
  container_reasons: dict[str, str]
```

#### `describe_ecs_container_instances`
```python
# For EC2 launch type clusters — inspect the underlying EC2 hosts
Input:
  cluster: str
  container_instance_ids: list[str] = None
Output:
  instances: list[ContainerInstanceDetail]
  # ec2_instance_id, status, registered/remaining CPU+memory, agent version
```

---

### 4.4 EC2 Tools

#### `describe_instances`
```python
Input:
  instance_ids: list[str] = None
  filters: list[Filter] = None  # e.g. tag:Environment=prod
Output:
  instances: list[InstanceSummary]
```

#### `describe_security_groups`
```python
Input:
  group_ids: list[str] = None
  filters: list[Filter] = None
Output:
  security_groups: list[SecurityGroupDetail]  # inbound/outbound rules
```

#### `describe_vpcs`
```python
Input:
  vpc_ids: list[str] = None
Output:
  vpcs: list[VPCSummary]
```

#### `describe_autoscaling_groups`
```python
Input:
  group_names: list[str] = None
Output:
  groups: list[ASGDetail]
  # min/max/desired, instances, scaling policies, activities (last 20)
```

---

### 4.5 RDS / Aurora Tools

#### `describe_db_instances`
```python
Input:
  db_instance_identifier: str = None
Output:
  instances: list[DBInstanceDetail]
  # engine, version, status, endpoint, AZ, multi-az, storage, parameter group
```

#### `describe_db_clusters`
```python
# Aurora clusters
Input:
  db_cluster_identifier: str = None
Output:
  clusters: list[DBClusterDetail]
  # members, reader/writer endpoints, engine version, status, backup retention
```

#### `describe_db_events`
```python
Input:
  source_identifier: str
  source_type: str             # db-instance | db-cluster | db-snapshot
  start_time: datetime
  end_time: datetime
Output:
  events: list[DBEvent]
```

#### `get_rds_log_file_portion`
```python
# Retrieve recent RDS/Aurora PostgreSQL log content (slow queries, errors)
Input:
  db_instance_identifier: str
  log_file_name: str           # from describe_db_log_files
  number_of_lines: int = 200
Output:
  log_data: str
```

---

### 4.6 DynamoDB Tools

#### `describe_dynamodb_table`
```python
Input:
  table_name: str
Output:
  table: TableDetail
  # status, item count, size, billing mode, GSIs, LSIs, TTL, encryption, streams
```

#### `list_dynamodb_tables`
```python
Output:
  table_names: list[str]
```

#### `get_dynamodb_metrics`
```python
# Convenience wrapper: fetches key CW metrics for a DynamoDB table in one call
Input:
  table_name: str
  start_time: datetime
  end_time: datetime
Output:
  metrics: dict
  # ConsumedReadCapacityUnits, ConsumedWriteCapacityUnits,
  # ThrottledRequests, SystemErrors, SuccessfulRequestLatency (P50/P99)
```

---

### 4.7 S3 Tools

#### `list_buckets`
```python
Output:
  buckets: list[BucketSummary]  # name, creation date, region
```

#### `get_bucket_metadata`
```python
# Aggregates versioning, encryption, public access block, replication, lifecycle
Input:
  bucket_name: str
Output:
  metadata: BucketMetadata
```

#### `get_bucket_policy`
```python
Input:
  bucket_name: str
Output:
  policy: dict                  # parsed JSON policy document
  public_access_block: PublicAccessBlockConfig
```

#### `get_s3_metrics`
```python
# Fetches CW Storage + Request metrics for a bucket
Input:
  bucket_name: str
  start_time: datetime
  end_time: datetime
Output:
  metrics: dict
  # BucketSizeBytes, NumberOfObjects, AllRequests, 4xxErrors, 5xxErrors
```

---

### 4.8 SQS Tools

#### `list_queues`
```python
Input:
  queue_name_prefix: str = None
Output:
  queue_urls: list[str]
```

#### `get_queue_attributes`
```python
Input:
  queue_url: str
Output:
  attributes: QueueAttributes
  # ApproximateNumberOfMessages, ApproximateNumberOfMessagesNotVisible,
  # ApproximateNumberOfMessagesDelayed, MessageRetentionPeriod,
  # VisibilityTimeout, RedrivePolicy (DLQ ARN + maxReceiveCount),
  # ApproximateAgeOfOldestMessage
```

#### `get_sqs_dead_letter_source_queues`
```python
Input:
  dead_letter_queue_url: str
Output:
  source_queues: list[str]
```

---

### 4.9 SNS Tools

#### `list_topics`
```python
Output:
  topics: list[TopicSummary]   # ARN, name
```

#### `get_topic_attributes`
```python
Input:
  topic_arn: str
Output:
  attributes: TopicAttributes
  # subscriptions (confirmed/pending/deleted), delivery policy,
  # KMS key ID, fifo settings
```

---

### 4.10 ALB / NLB Tools

#### `describe_load_balancers`
```python
Input:
  names: list[str] = None
  arns: list[str] = None
  type_filter: str = None      # application | network
Output:
  load_balancers: list[LBSummary]
  # scheme, vpc, AZs, state, DNS name, type
```

#### `describe_listeners`
```python
Input:
  load_balancer_arn: str
Output:
  listeners: list[ListenerDetail]  # port, protocol, default actions, rules count
```

#### `describe_target_groups`
```python
Input:
  load_balancer_arn: str = None
  target_group_arns: list[str] = None
Output:
  target_groups: list[TargetGroupDetail]
  # protocol, port, health check settings, healthy/unhealthy threshold
```

#### `describe_target_health`
```python
Input:
  target_group_arn: str
Output:
  targets: list[TargetHealthDetail]
  # target id, port, health state, reason code (for unhealthy targets)
```

---

### 4.11 API Gateway Tools

#### `list_rest_apis`
```python
Output:
  apis: list[RestAPISummary]   # id, name, endpoint type, created date
```

#### `get_stages`
```python
Input:
  rest_api_id: str
Output:
  stages: list[StageDetail]
  # stage name, deployment id, throttling, caching, logging, WAF association
```

#### `get_api_gateway_metrics`
```python
# Fetches key CW metrics for an API stage
Input:
  rest_api_id: str
  stage_name: str
  start_time: datetime
  end_time: datetime
Output:
  metrics: dict
  # Count, 4XXError, 5XXError, Latency (P50/P99), IntegrationLatency, CacheHitCount
```

---

### 4.12 CloudFront Tools

#### `list_distributions`
```python
Output:
  distributions: list[DistributionSummary]
  # id, domain name, origins, aliases (CNAMEs), status, price class
```

#### `get_distribution_config`
```python
Input:
  distribution_id: str
Output:
  config: DistributionConfig
  # origins (S3/custom), behaviors (cache policies, TTLs, allowed methods),
  # WAF, geo restriction, SSL cert, HTTP version
```

---

### 4.13 Lambda Tools

#### `list_lambda_functions`
```python
Output:
  functions: list[FunctionSummary]  # name, runtime, memory, timeout, last modified
```

#### `get_function_configuration`
```python
Input:
  function_name: str
Output:
  config: FunctionConfig
  # runtime, handler, role, timeout, memory, env vars (keys only, values redacted),
  # layers, VPC config, reserved concurrency, architectures
```

#### `get_lambda_metrics`
```python
# Fetches key CW metrics for a Lambda function
Input:
  function_name: str
  start_time: datetime
  end_time: datetime
Output:
  metrics: dict
  # Invocations, Errors, Throttles, Duration (P50/P99/Max),
  # ConcurrentExecutions, UnreservedConcurrentExecutions
```

---

### 4.14 Step Functions Tools

#### `list_state_machines`
```python
Output:
  state_machines: list[StateMachineSummary]  # ARN, name, type (STANDARD|EXPRESS), created
```

#### `describe_state_machine`
```python
Input:
  state_machine_arn: str
Output:
  definition: dict             # ASL definition (parsed JSON)
  status: str
  role_arn: str
  logging_config: LoggingConfig
  tracing_config: TracingConfig
```

#### `list_executions`
```python
Input:
  state_machine_arn: str
  status_filter: str = None    # RUNNING | SUCCEEDED | FAILED | TIMED_OUT | ABORTED
  max_results: int = 20
Output:
  executions: list[ExecutionSummary]
  # execution ARN, name, status, start/stop time

# Follow-up: get_execution_history(execution_arn) for full event trace
```

#### `get_execution_history`
```python
Input:
  execution_arn: str
  max_results: int = 100
Output:
  events: list[ExecutionEvent]
  # Full step-by-step event trace including failed state details and cause/error fields
```

---

### 4.15 AWS Glue Tools

#### `list_glue_jobs`
```python
Output:
  jobs: list[GlueJobSummary]   # name, role, command (script location), created
```

#### `get_glue_job_runs`
```python
Input:
  job_name: str
  max_results: int = 20
Output:
  runs: list[JobRunDetail]
  # run id, status, start/end time, error message, DPU capacity, execution time
```

#### `get_glue_crawlers`
```python
Input:
  crawler_name: str = None
Output:
  crawlers: list[CrawlerDetail]
  # state, schedule, last crawl status, last crawl error message, targets
```

---

### 4.16 ElastiCache Tools

#### `describe_cache_clusters`
```python
Input:
  cache_cluster_id: str = None
Output:
  clusters: list[CacheClusterDetail]
  # engine (Redis|Memcached), version, status, node type, num nodes,
  # endpoint, parameter group, maintenance window
```

#### `get_elasticache_metrics`
```python
# Fetches key CW metrics for a Redis/Memcached cluster
Input:
  cache_cluster_id: str
  start_time: datetime
  end_time: datetime
Output:
  metrics: dict
  # CurrConnections, Evictions, CacheHits, CacheMisses, CacheHitRate,
  # FreeableMemory, NetworkBytesIn/Out, ReplicationLag (Redis)
```

---

### 4.17 ECR Tools

#### `list_repositories`
```python
Output:
  repositories: list[RepositorySummary]  # name, URI, created, image tag mutability
```

#### `describe_images`
```python
Input:
  repository_name: str
  image_ids: list[ImageIdentifier] = None  # digest or tag
  max_results: int = 20
Output:
  images: list[ImageDetail]
  # digest, tags, pushed_at, size, scan findings summary (if scan-on-push enabled)
```

---

### 4.18 KMS Tools (Customer Managed Keys)

#### `list_kms_keys`
```python
Output:
  keys: list[KeySummary]        # key ID, ARN
```

#### `describe_kms_key`
```python
Input:
  key_id: str                   # key ID or ARN or alias
Output:
  metadata: KeyMetadata
  # description, state (Enabled|Disabled|PendingDeletion), creation date,
  # key usage, key spec, origin, rotation status, key policy summary
```

---

### 4.19 Secrets Manager Tools

#### `list_secrets`
```python
# Returns secret metadata ONLY — no secret values are ever retrieved
Input:
  filters: list[Filter] = None
Output:
  secrets: list[SecretSummary]
  # name, ARN, last changed, last rotated, rotation enabled, KMS key ID
  # NOTE: SecretString / SecretBinary values are NEVER fetched
```

---

### 4.20 IAM Tools

#### `get_role`
```python
Input:
  role_name: str
Output:
  role: RoleDetail
  # ARN, trust policy, attached managed policies (names + ARNs),
  # inline policy names, last used date
  # NOTE: policy documents are not expanded to avoid sensitive data exposure
```

#### `simulate_principal_policy`
```python
# Answer "does role X have permission to do Y on resource Z?"
Input:
  policy_source_arn: str        # role or user ARN
  action_names: list[str]       # e.g. ["s3:GetObject", "kms:Decrypt"]
  resource_arns: list[str]
Output:
  results: list[EvaluationResult]
  # allowed/denied per action, matched statements, organizations/SCP context
```

---

### 4.21 ACM Tools

#### `list_certificates`
```python
Input:
  certificate_statuses: list[str] = None  # ISSUED | EXPIRED | PENDING_VALIDATION
Output:
  certificates: list[CertSummary]  # ARN, domain, status, type (Amazon|Imported)
```

#### `describe_certificate`
```python
Input:
  certificate_arn: str
Output:
  certificate: CertDetail
  # domains (SANs), status, not_before, not_after, issuer, key algorithm,
  # renewal eligibility, in-use-by (ALB/CloudFront ARNs)
```

---

### 4.22 Route 53 Tools

#### `list_hosted_zones`
```python
Output:
  zones: list[HostedZoneSummary]  # id, name, private/public, record count
```

#### `list_resource_record_sets`
```python
Input:
  hosted_zone_id: str
  start_record_name: str = None  # pagination / targeted lookup
  max_items: int = 100
Output:
  record_sets: list[RecordSetDetail]
  # name, type (A/CNAME/ALIAS/MX/TXT), TTL, values / alias target
```

---

### 4.23 SES Tools

#### `get_send_statistics`
```python
# Returns delivery attempt metrics for the past 2 weeks (SES native window)
Output:
  data_points: list[SendDataPoint]
  # timestamp, delivery_attempts, bounces, complaints, rejects
```

#### `get_account_sending_enabled`
```python
Output:
  enabled: bool
  sending_quota: SendingQuota   # max_24hr_send, max_send_rate, sent_last_24hr
  suppression_attributes: dict  # suppression list reasons (BOUNCE | COMPLAINT)
```

---

### 4.24 CloudTrail Tools

#### `lookup_cloudtrail_events`
```python
Input:
  lookup_attributes: list[LookupAttribute]
  # EventName, ResourceName, ResourceType, Username, AccessKeyId, EventId, ReadOnly
  start_time: datetime
  end_time: datetime
  max_results: int = 50
Output:
  events: list[CloudTrailEvent]
  # event time, name, source, user identity, source IP, request/response params
```

#### `get_trail_status`
```python
Input:
  trail_name: str
Output:
  status: TrailStatus
  # is_logging, latest_delivery_time, latest_notification_time,
  # latest_delivery_error, start_logging_time
```

---

### 4.25 Resource Discovery Tool

#### `list_tagged_resources`
```python
# AWS Resource Groups Tagging API — cross-service resource discovery
Input:
  tag_filters: list[TagFilter]       # e.g. [{"Key": "Environment", "Values": ["prod"]}]
  resource_type_filters: list[str] = None
  # e.g. ["ecs:service", "rds:db", "lambda:function", "sqs:queue"]
Output:
  resources: list[ResourceSummary]   # ARN, resource type, tags
```

---

## 5. Chat Interface

### 5.1 Features

| Feature | Description |
|---------|-------------|
| Conversation threads | Each triage session is a named thread; threads are persisted |
| Streaming responses | Agent tokens and tool-call events stream in real time |
| Tool call transparency | Collapsible "Evidence Trail" panel shows every tool invoked, its inputs, and outputs |
| Markdown rendering | Diagnosis responses render code blocks, tables, lists |
| Copy to clipboard | One-click copy for Terraform snippets, commands, log queries |
| Session history | Left sidebar lists prior sessions by date/description |
| New session | Button to start a fresh triage thread |
| Dark mode | Terminal-aesthetic dark theme appropriate for ops use |

### 5.2 Streaming Protocol

Uses **Server-Sent Events (SSE)** over HTTP (API Gateway HTTP API) for simplicity and reliability over WebSocket.

Event types streamed from agent to UI:

```
event: token
data: {"text": "Analyzing your CloudWatch logs..."}

event: tool_start
data: {"tool": "query_cloudwatch_logs", "input": {...}}

event: tool_end
data: {"tool": "query_cloudwatch_logs", "output": {...}, "duration_ms": 1240}

event: clarification
data: {"question": "Which ECS cluster are you referring to?"}

event: done
data: {"session_id": "sess_abc123", "total_tokens": 4821}
```

### 5.3 UI Layout

```
┌────────────────────────────────────────────────────────────────┐
│  [≡] AWS Triage Agent                          [New Session]   │
├──────────────┬─────────────────────────────────────────────────┤
│ Sessions     │  Current Session: "ECS task OOM - prod 2025-06"│
│              ├─────────────────────────────────────────────────┤
│ > Today      │                                                  │
│   ECS OOM    │   ┌─────────────────────────────────────────┐  │
│   RDS slow   │   │ 🤖 Agent                                │  │
│              │   │ I can see the payment-service ECS tasks  │  │
│ > Yesterday  │   │ are stopping with exit code 137 (OOM).   │  │
│   Lambda err │   │                                          │  │
│   Deploy fail│   │ ▼ Evidence Trail (3 tool calls)          │  │
│              │   │   ├─ list_ecs_clusters → [prod-cluster]  │  │
│              │   │   ├─ describe_ecs_tasks → 4 stopped      │  │
│              │   │   └─ query_cloudwatch_logs → OOM entries │  │
│              │   └─────────────────────────────────────────┘  │
│              │                                                  │
│              │   ┌─────────────────────────────────────────┐  │
│              │   │  Root Cause: Memory limit (512MB) too   │  │
│              │   │  low for current traffic. P99 heap usage │  │
│              │   │  was 498MB before OOM kill.              │  │
│              │   │                                          │  │
│              │   │  Recommended Fix (Terraform):            │  │
│              │   │  ```hcl                                   │  │
│              │   │  memory = 1024                           │  │
│              │   │  ```                              [Copy] │  │
│              │   └─────────────────────────────────────────┘  │
│              ├─────────────────────────────────────────────────┤
│              │  [Ask a follow-up or describe a new issue...]   │
│              │                                          [Send] │
└──────────────┴─────────────────────────────────────────────────┘
```

---

## 6. Data Model

### 6.1 DynamoDB Schema

**Table: `triage-sessions`**

```
PK: user_id#{user_id}
SK: session#{session_id}

Attributes:
  session_id: str (UUID)
  user_id: str
  title: str                 # Auto-generated from first message
  created_at: ISO8601
  updated_at: ISO8601
  status: ACTIVE | CLOSED
  message_count: int
```

**Table: `triage-messages`**

```
PK: session#{session_id}
SK: msg#{timestamp}#{message_id}

Attributes:
  message_id: str (UUID)
  session_id: str
  role: USER | ASSISTANT | TOOL
  content: str               # Markdown text
  tool_calls: list[ToolCall] # If role=ASSISTANT with tool use
  tool_result: dict          # If role=TOOL
  tokens_used: int
  created_at: ISO8601
```

**GSI:** `user-sessions-index` on `user_id` + `created_at` for session listing.

---

## 7. Infrastructure (Terraform)

### 7.1 Module Structure

```
terraform/
├── main.tf
├── variables.tf
├── outputs.tf
├── providers.tf
│
├── modules/
│   ├── networking/           # VPC, subnets, SGs (or uses existing)
│   ├── ecs/                  # ECS cluster, Fargate task def, service
│   ├── api_gateway/          # HTTP API + SSE routes
│   ├── frontend/             # S3 bucket + CloudFront distribution
│   ├── dynamodb/             # Sessions + messages tables
│   ├── iam/                  # Agent IAM role + policies
│   └── ecr/                  # Container registry
│
└── environments/
    ├── dev/
    │   └── terraform.tfvars
    └── prod/
        └── terraform.tfvars
```

### 7.2 ECS Fargate Task Definition (Key Settings)

```hcl
resource "aws_ecs_task_definition" "triage_agent" {
  family                   = "triage-agent"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024   # 1 vCPU
  memory                   = 2048   # 2 GB

  task_role_arn      = aws_iam_role.agent_task_role.arn
  execution_role_arn = aws_iam_role.ecs_execution_role.arn

  container_definitions = jsonencode([{
    name  = "triage-agent"
    image = "${aws_ecr_repository.triage_agent.repository_url}:latest"
    portMappings = [{ containerPort = 8000 }]
    environment = [
      { name = "AWS_REGION",         value = var.aws_region },
      { name = "DYNAMODB_TABLE_SESSIONS", value = aws_dynamodb_table.sessions.name },
      { name = "DYNAMODB_TABLE_MESSAGES", value = aws_dynamodb_table.messages.name },
      { name = "BEDROCK_MODEL_ID",   value = "anthropic.claude-sonnet-4-20250514-v1:0" },
      { name = "MAX_TOOL_ITERATIONS", value = "15" }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = "/ecs/triage-agent"
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}
```

### 7.3 Agent IAM Role Policy

```hcl
# Read-only policy for CloudWatch Logs
resource "aws_iam_role_policy" "cloudwatch_logs" {
  role = aws_iam_role.agent_task_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:GetLogEvents",
        "logs:FilterLogEvents",
        "logs:StartQuery",
        "logs:StopQuery",
        "logs:GetQueryResults",
        "logs:GetLogGroupFields",
      ]
      Resource = "*"
    }]
  })
}

# Read-only policy for AWS service APIs — covers all monitored services
resource "aws_iam_role_policy" "aws_read_only" {
  role = aws_iam_role.agent_task_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        # CloudWatch Logs
        "logs:DescribeLogGroups", "logs:DescribeLogStreams",
        "logs:GetLogEvents", "logs:FilterLogEvents",
        "logs:StartQuery", "logs:StopQuery", "logs:GetQueryResults",
        "logs:GetLogGroupFields",
        # CloudWatch Metrics & Alarms
        "cloudwatch:GetMetricStatistics", "cloudwatch:GetMetricData",
        "cloudwatch:ListMetrics", "cloudwatch:DescribeAlarms",
        "cloudwatch:DescribeAlarmHistory",
        # ECS
        "ecs:ListClusters", "ecs:ListServices", "ecs:ListTasks",
        "ecs:DescribeClusters", "ecs:DescribeServices",
        "ecs:DescribeTasks", "ecs:DescribeTaskDefinition",
        "ecs:DescribeContainerInstances", "ecs:ListContainerInstances",
        # EC2
        "ec2:DescribeInstances", "ec2:DescribeSecurityGroups",
        "ec2:DescribeVpcs", "ec2:DescribeSubnets",
        "ec2:DescribeNetworkInterfaces",
        # Auto Scaling
        "autoscaling:DescribeAutoScalingGroups",
        "autoscaling:DescribeScalingActivities",
        "autoscaling:DescribePolicies",
        # RDS / Aurora
        "rds:DescribeDBInstances", "rds:DescribeDBClusters",
        "rds:DescribeEvents", "rds:DescribeDBLogFiles",
        "rds:DownloadDBLogFilePortion", "rds:DescribeDBParameters",
        "rds:DescribeDBClusterParameters",
        # DynamoDB
        "dynamodb:ListTables", "dynamodb:DescribeTable",
        "dynamodb:DescribeTimeToLive", "dynamodb:ListTagsOfResource",
        # S3
        "s3:ListAllMyBuckets", "s3:GetBucketLocation",
        "s3:GetBucketVersioning", "s3:GetBucketEncryption",
        "s3:GetBucketPublicAccessBlock", "s3:GetBucketPolicy",
        "s3:GetBucketReplication", "s3:GetBucketLogging",
        "s3:GetLifecycleConfiguration", "s3:GetBucketTagging",
        # SQS
        "sqs:ListQueues", "sqs:GetQueueAttributes",
        "sqs:ListDeadLetterSourceQueues", "sqs:ListQueueTags",
        # SNS
        "sns:ListTopics", "sns:GetTopicAttributes",
        "sns:ListSubscriptionsByTopic",
        # Load Balancers (ALB + NLB)
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeTargetGroups",
        "elasticloadbalancing:DescribeTargetHealth",
        "elasticloadbalancing:DescribeListeners",
        "elasticloadbalancing:DescribeRules",
        "elasticloadbalancing:DescribeLoadBalancerAttributes",
        "elasticloadbalancing:DescribeTargetGroupAttributes",
        # API Gateway
        "apigateway:GET",
        # CloudFront
        "cloudfront:ListDistributions",
        "cloudfront:GetDistributionConfig",
        "cloudfront:GetDistribution",
        # Lambda
        "lambda:ListFunctions", "lambda:GetFunction",
        "lambda:GetFunctionConfiguration",
        "lambda:GetFunctionConcurrency",
        "lambda:ListEventSourceMappings",
        # Step Functions
        "states:ListStateMachines", "states:DescribeStateMachine",
        "states:ListExecutions", "states:GetExecutionHistory",
        "states:DescribeExecution",
        # AWS Glue
        "glue:ListJobs", "glue:GetJob", "glue:GetJobRuns",
        "glue:GetCrawlers", "glue:GetCrawler",
        # ElastiCache
        "elasticache:DescribeCacheClusters",
        "elasticache:DescribeReplicationGroups",
        "elasticache:DescribeCacheParameters",
        "elasticache:DescribeEvents",
        # ECR
        "ecr:DescribeRepositories", "ecr:DescribeImages",
        "ecr:GetRepositoryPolicy", "ecr:ListImages",
        # KMS (Customer Managed Keys)
        "kms:ListKeys", "kms:DescribeKey",
        "kms:GetKeyPolicy", "kms:GetKeyRotationStatus",
        "kms:ListAliases",
        # Secrets Manager (metadata ONLY — no GetSecretValue)
        "secretsmanager:ListSecrets",
        "secretsmanager:DescribeSecret",
        # IAM (read-only, no policy document expansion)
        "iam:GetRole", "iam:ListAttachedRolePolicies",
        "iam:ListRolePolicies", "iam:SimulatePrincipalPolicy",
        "iam:GetRolePolicy",
        # ACM
        "acm:ListCertificates", "acm:DescribeCertificate",
        # Route 53
        "route53:ListHostedZones",
        "route53:ListResourceRecordSets",
        "route53:GetHostedZone",
        # SES
        "ses:GetSendStatistics", "ses:GetSendQuota",
        "ses:GetAccountSendingEnabled",
        "sesv2:GetAccount", "sesv2:ListSuppressedDestinations",
        # CloudTrail
        "cloudtrail:LookupEvents", "cloudtrail:GetTrailStatus",
        "cloudtrail:DescribeTrails",
        # SSM (parameter names only — no SecureString values)
        "ssm:DescribeParameters", "ssm:GetParametersByPath",
        # Resource Groups Tagging (cross-service discovery)
        "tag:GetResources", "tag:GetTagKeys", "tag:GetTagValues",
        # Resource Groups
        "resource-groups:ListGroups",
        "resource-groups:GetGroup",
      ]
      Resource = "*"
    }]
  })
}

# DynamoDB access (sessions + messages tables only)
resource "aws_iam_role_policy" "dynamodb" {
  role = aws_iam_role.agent_task_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
                  "dynamodb:Query", "dynamodb:Scan"]
      Resource = [
        aws_dynamodb_table.sessions.arn,
        aws_dynamodb_table.messages.arn,
        "${aws_dynamodb_table.sessions.arn}/index/*",
        "${aws_dynamodb_table.messages.arn}/index/*",
      ]
    }]
  })
}

# Bedrock invocation
resource "aws_iam_role_policy" "bedrock" {
  role = aws_iam_role.agent_task_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = "arn:aws:bedrock:${var.aws_region}::foundation-model/anthropic.claude-*"
    }]
  })
}
```

### 7.4 Networking

The agent runs in an **existing VPC** injected via Terraform input variables — no new VPC is created. The networking module performs **data-only lookups** using `aws_vpc`, `aws_subnets`, and `aws_security_group` data sources.

The agent Fargate task runs in **existing private subnets** with no direct internet exposure. API Gateway is the only ingress point via a VPC Link. VPC interface endpoints for Bedrock, DynamoDB, CloudWatch, ECR, and SSM are created only if they don't already exist (use `aws_vpc_endpoint` with a `lifecycle { prevent_destroy = true }` guard or a separate `create_vpc_endpoints` toggle variable).

```
Internet → CloudFront (SPA) → S3
Internet → API Gateway (HTTP API) → VPC Link → ALB → ECS Fargate (existing private subnet)

ECS Fargate (private) → VPC Endpoint → Bedrock
ECS Fargate (private) → VPC Endpoint → DynamoDB
ECS Fargate (private) → VPC Endpoint → CloudWatch / ECR / SSM
```

**Required Terraform input variables for networking:**

```hcl
variable "vpc_id" {
  description = "ID of the existing VPC to deploy into"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of existing private subnet IDs for ECS Fargate tasks"
  type        = list(string)
}

variable "public_subnet_ids" {
  description = "List of existing public subnet IDs for the ALB"
  type        = list(string)
}

variable "create_vpc_endpoints" {
  description = "Set to false if VPC endpoints for Bedrock/DynamoDB/CW already exist"
  type        = bool
  default     = true
}
```

The networking module will **not** manage route tables, internet gateways, or NAT gateways — those are assumed to already exist in the provided VPC.

---

## 8. Agent Service: Application Structure

```
agent-service/
├── Dockerfile
├── requirements.txt
│
├── app/
│   ├── main.py               # FastAPI app, SSE endpoint
│   ├── config.py             # Env var config (pydantic-settings)
│   │
│   ├── agent/
│   │   ├── graph.py          # LangGraph StateGraph definition
│   │   ├── nodes.py          # LangGraph node functions
│   │   ├── state.py          # AgentState TypedDict
│   │   └── prompts.py        # System prompt + node prompts
│   │
│   ├── tools/
│   │   ├── __init__.py       # Tool registry (all tools imported + listed)
│   │   ├── cloudwatch_logs.py        # 4.1  — CW Logs Insights
│   │   ├── cloudwatch_metrics.py     # 4.2  — CW Metrics & Alarms
│   │   ├── ecs.py                    # 4.3  — ECS (Fargate + EC2 launch type)
│   │   ├── ec2.py                    # 4.4  — EC2 + Auto Scaling
│   │   ├── rds.py                    # 4.5  — RDS / Aurora PostgreSQL
│   │   ├── dynamodb.py               # 4.6  — DynamoDB
│   │   ├── s3.py                     # 4.7  — S3 + bucket policies
│   │   ├── sqs.py                    # 4.8  — SQS + DLQ
│   │   ├── sns.py                    # 4.9  — SNS
│   │   ├── elb.py                    # 4.10 — ALB / NLB
│   │   ├── apigw.py                  # 4.11 — API Gateway
│   │   ├── cloudfront.py             # 4.12 — CloudFront
│   │   ├── lambda_.py                # 4.13 — Lambda
│   │   ├── stepfunctions.py          # 4.14 — Step Functions
│   │   ├── glue.py                   # 4.15 — AWS Glue
│   │   ├── elasticache.py            # 4.16 — ElastiCache (Redis/Memcached)
│   │   ├── ecr.py                    # 4.17 — ECR
│   │   ├── kms.py                    # 4.18 — KMS (Customer Managed Keys)
│   │   ├── secretsmanager.py         # 4.19 — Secrets Manager (metadata only)
│   │   ├── iam.py                    # 4.20 — IAM roles + policy simulation
│   │   ├── acm.py                    # 4.21 — ACM certificates
│   │   ├── route53.py                # 4.22 — Route 53 hosted zones + records
│   │   ├── ses.py                    # 4.23 — SES sending stats + quota
│   │   ├── cloudtrail.py             # 4.24 — CloudTrail events
│   │   └── tagging.py                # 4.25 — Resource Groups Tagging API
│   │
│   ├── memory/
│   │   ├── dynamodb_checkpointer.py  # LangGraph DynamoDB checkpointer
│   │   └── session_manager.py
│   │
│   └── api/
│       ├── routes.py          # /chat/stream, /sessions, /sessions/{id}
│       └── schemas.py         # Pydantic request/response models
```

### 8.1 Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat/stream` | Start or continue a session, stream SSE response |
| `GET`  | `/sessions` | List sessions for current user |
| `GET`  | `/sessions/{id}` | Retrieve full message history for a session |
| `DELETE` | `/sessions/{id}` | Delete a session |
| `GET`  | `/health` | ECS health check |

### 8.2 LangGraph State

```python
class AgentState(TypedDict):
    session_id: str
    messages: list[BaseMessage]          # Full conversation history
    tool_calls_made: int                  # Guard against infinite loops
    clarification_rounds: int             # Max 2
    investigation_plan: str               # LLM-generated plan text
    findings: list[Finding]               # Accumulated evidence
    final_diagnosis: Optional[Diagnosis]
    error: Optional[str]
```

---

## 9. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| Agent modifying resources | IAM role has zero write/mutate permissions. No `Create*`, `Update*`, `Delete*`, `Put*` (except DynamoDB own tables) |
| Prompt injection via log data | Tool outputs are always injected as `tool` role messages, never as `user` messages. System prompt instructs model to treat tool data as untrusted |
| Sensitive data in logs | SSM `GetParameter` only allowed for parameter discovery, not SecureString value retrieval. Agents cannot read Secrets Manager values |
| API abuse | API Gateway rate limiting (100 req/s per IP); JWT/Cognito authentication required |
| Container escape | Fargate provides VM-level isolation; no access to underlying host |
| Data exfiltration | Agent runs in private subnet; no outbound internet except via controlled VPC endpoints |

---

## 10. Authentication

The UI and API are protected by **Amazon Cognito** (User Pool + App Client):

- Users authenticate via Cognito Hosted UI (SAML/OIDC federation optional for SSO)
- JWT token attached to every API request
- API Gateway authorizer validates token
- `user_id` extracted from JWT `sub` claim for session scoping

---

## 11. Observability

| Signal | Tooling |
|--------|---------|
| Agent service logs | CloudWatch Logs (`/ecs/triage-agent`) |
| Distributed traces | AWS X-Ray (LangChain instrumented) |
| Tool call latency | Custom CloudWatch metrics per tool name |
| Token usage | CloudWatch metrics: `InputTokens`, `OutputTokens` per session |
| Error rate | CloudWatch alarm: `5xx` from API Gateway |
| ECS health | CloudWatch Container Insights |

---

## 12. Deployment Flow

```
Developer → git push → CI/CD (GitHub Actions / CodePipeline)
  → docker build + push to ECR
  → terraform plan (PR comment)
  → terraform apply (on merge to main)
  → ECS rolling deploy (new task def revision)
  → CloudFront invalidation (SPA)
```

---

## 13. Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region |
| `BEDROCK_MODEL_ID` | `anthropic.claude-sonnet-4-20250514-v1:0` | Bedrock model |
| `MAX_TOOL_ITERATIONS` | `15` | Max tool calls per agent loop |
| `MAX_CLARIFICATION_ROUNDS` | `2` | Max rounds of clarification before proceeding |
| `SESSION_TTL_DAYS` | `30` | DynamoDB TTL for sessions |
| `STREAM_TIMEOUT_SECONDS` | `300` | Max SSE connection duration |
| `LOG_QUERY_MAX_RECORDS` | `1000` | Max records per CW Logs Insights query |

---

## 14. Out of Scope (v1)

- **Write remediation actions** — agent recommends only; no automated apply
- **Multi-account** — single AWS account only in v1; cross-account assumeRole pattern deferred
- **Slack/PagerDuty integration** — chat UI only in v1
- **Scheduled / alert-triggered triage** — user-initiated only in v1
- **Cost anomaly detection** — Cost Explorer APIs not included in v1
- **Vector search over log history** — full-text semantic search across past sessions deferred

---

## 15. Open Questions / Decisions Needed

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| 1 | Auth provider | Cognito vs existing IdP (Okta/AzureAD) | Cognito with SAML if IdP exists |
| 2 | SSE vs WebSocket | SSE simpler, WebSocket for bidirectional | SSE sufficient; WS if real-time cancel needed |
| 3 | VPC: new vs existing | Create new or inject into existing | ✅ **Decided: inject into existing VPC via input variables** |
| 4 | Multi-env (dev/prod) | Separate accounts or same account | Separate Terraform workspaces minimum |
| 5 | Log retention | How long to keep triage sessions? | 30 days default, configurable |
| 6 | User management | Self-service signup vs admin-provisioned | Admin-provisioned (internal tool) |

---

*End of Specification v1.0.0*
