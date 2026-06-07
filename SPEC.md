# AWS Triage Agent — Application Specification

**Version:** 1.1.0  
**Status:** MVP Implementation / Active Build  
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
- **Portable build.** The agent is built and tested locally (Docker Compose + LocalStack), committed to GitHub, and pulled into the target AWS environment for deployment. Local development can use OpenAI for LLM calls and mock AWS tool responses; the deployed work environment uses AWS Bedrock.

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
                        │ HTTPS / SSE (API Gateway HTTP API)
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
│  │                       │  │  - EC2/VPC/SG/Subnet │   │  │  │
│  │                       │  │  - RDS Describe      │   │  │  │
│  │                       │  │  - ELB Describe      │   │  │  │
│  │                       │  │  - Lambda Describe   │   │  │  │
│  │                       │  │  - CloudTrail Events │   │  │  │
│  │                       │  │  - SSM Parameters    │   │  │  │
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
| Chat UI | React + TypeScript + Tailwind + Chatscope UI Kit | Simple chat interface; pre-built components to minimise frontend dev work |
| Static Hosting | S3 + CloudFront | Serve the SPA globally |
| API Layer | API Gateway (HTTP API) | Route chat messages; stream agent responses via SSE |
| Agent Service | FastAPI + LangGraph + Python | Core agentic loop + tool execution |
| LLM | OpenAI locally; AWS Bedrock in deployed AWS | Reasoning, tool-call orchestration, diagnosis |
| Conversation State | DynamoDB | Persist session history, tool call logs |
| Infrastructure | Terraform | All AWS resources defined as code |
| Container Registry | ECR | Agent Docker image |
| Secrets | AWS Secrets Manager | API keys, config (if any) |
| Observability | CloudWatch Logs + X-Ray | Agent's own telemetry |
| Local Dev | Docker Compose + LocalStack + OpenAI | Run the full stack locally; use `MOCK_AWS=true` for fake AWS tool data or read-only AWS credentials for real AWS APIs |

### 2.3 Deployment Model

The agent codebase is developed and tested **locally** (Docker Compose + LocalStack), then:

```
Local dev (Docker Compose + LocalStack)
  → git push to GitHub
  → GitHub Actions CI (lint, test, docker build, push to ECR)
  → Pull into target AWS environment → terraform apply → ECS deploy
```

The **developer does not need access to the target AWS account**. The target environment pulls the image from ECR and runs it. AWS credentials for the target account are stored as GitHub Actions secrets and used only in CI/CD.

---

## 3. Agent Design

### 3.1 Agent Framework: LangGraph

LangGraph is chosen because:
- Native support for **cyclic graphs** (the agent loop with tool calls)
- First-class **streaming** support — tokens and tool events stream back to the UI
- Tool-calling with OpenAI locally via `ChatOpenAI`
- Tool-calling with AWS Bedrock in AWS deployments via `ChatBedrockConverse`

Current MVP state is persisted by the application session manager in DynamoDB. LangGraph process-local checkpointing is intentionally not used, so ECS restarts do not leave the graph with divergent in-memory state.

### 3.2 Agent State Machine

**Current MVP implementation:** a compact two-node LangGraph loop:

```
START
  -> agent node (LLM bound to all read-only AWS tools)
  -> tools node (execute requested tool calls)
  -> agent node (continue reasoning with tool output)
  -> END when no tool calls remain or MAX_TOOL_ITERATIONS is reached
```

The richer classifier / planner / synthesizer graph below remains the target design for a later hardening phase.

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

**Coverage summary (26 services → 62 tools):**

| # | Service | Tools | File |
|---|---------|-------|------|
| 1 | CloudWatch Logs | 4 | `cloudwatch_logs.py` |
| 2 | CloudWatch Metrics & Alarms | 3 | `cloudwatch_metrics.py` |
| 3 | ECS (Fargate + EC2 launch type) | 5 | `ecs.py` |
| 4 | EC2 + VPC + Subnets + Security Groups + ASG | 5 | `ec2.py` |
| 5 | RDS / Aurora | 4 | `rds.py` |
| 6 | DynamoDB | 3 | `dynamodb.py` |
| 7 | S3 | 4 | `s3.py` |
| 8 | SQS | 3 | `sqs.py` |
| 9 | SNS | 2 | `sns.py` |
| 10 | ALB / NLB | 4 | `elb.py` |
| 11 | API Gateway | 3 | `apigw.py` |
| 12 | CloudFront | 2 | `cloudfront.py` |
| 13 | Lambda | 3 | `lambda_.py` |
| 14 | Step Functions | 4 | `stepfunctions.py` |
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
| 25 | SSM Parameter Store | 2 | `ssm.py` |
| 26 | Resource Tagging (discovery) | 1 | `tagging.py` |

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

### 4.4 EC2 / VPC / Networking Tools

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
  vpcs: list[VPCSummary]       # CIDR, state, tags, DHCP options
```

#### `describe_subnets`
```python
Input:
  subnet_ids: list[str] = None
  filters: list[Filter] = None  # e.g. vpc-id, availability-zone
Output:
  subnets: list[SubnetSummary]
  # subnet_id, vpc_id, cidr_block, availability_zone,
  # available_ip_count, map_public_ip_on_launch, tags
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
```

#### `get_execution_history`
```python
# Separate registered tool — fetches the full step-by-step event trace for one execution
Input:
  execution_arn: str
  max_results: int = 100
Output:
  events: list[ExecutionEvent]
  # Full event trace including failed state details, cause, and error fields
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

### 4.25 SSM Parameter Store Tools

#### `describe_ssm_parameters`
```python
# Lists parameter metadata — parameter values are NOT retrieved
Input:
  filters: list[ParameterFilter] = None  # e.g. Name contains "/prod/myapp"
  max_results: int = 50
Output:
  parameters: list[ParameterMetadata]
  # name, type (String|StringList|SecureString), last_modified, ARN, tier
  # NOTE: SecureString values are NEVER fetched
```

#### `get_parameters_by_path`
```python
# Returns plaintext String/StringList parameters under a path prefix
# SecureString parameters are returned with Value="[REDACTED]"
Input:
  path: str                    # e.g. /prod/myapp/
  recursive: bool = True
Output:
  parameters: list[Parameter]
  # name, type, value (SecureString values redacted), version, last_modified
```

---

### 4.26 Resource Discovery Tool

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

### 5.1 UI Philosophy

The UI is a **minimal chat interface** — the value is in the agent's intelligence, not the frontend. To minimise frontend development effort, the UI uses [`@chatscope/chat-ui-kit-react`](https://chatscope.io/) for pre-built chat components (message list, input box, typing indicator) and adds only the custom pieces the spec requires (session sidebar, Evidence Trail panel).

No custom design system. Tailwind for layout and dark theme only.

### 5.2 Features

| Feature | Description |
|---------|-------------|
| Conversation threads | Each triage session is a named thread; threads are persisted |
| Streaming responses | Agent tokens stream in real time via SSE |
| Tool call transparency | Collapsible "Evidence Trail" panel shows every tool invoked, its inputs, and outputs |
| Markdown rendering | Diagnosis responses render code blocks, tables, lists |
| Copy to clipboard | One-click copy for Terraform snippets, commands, log queries |
| Session history | Left sidebar lists prior sessions; title is the first 80 chars of the user's opening message |
| New session | Button to start a fresh triage thread |
| Dark mode | Terminal-aesthetic dark theme |

### 5.3 Streaming Protocol

Uses **Server-Sent Events (SSE)** over HTTP (API Gateway HTTP API).

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

### 5.4 UI Layout

```
┌────────────────────────────────────────────────────────────────┐
│  [≡] AWS Triage Agent                          [New Session]   │
├──────────────┬─────────────────────────────────────────────────┤
│ Sessions     │  Current Session: "ECS task OOM - prod 2025-06"│
│              ├─────────────────────────────────────────────────┤
│ > Today      │                                                  │
│   ECS OOM    │   ┌─────────────────────────────────────────┐  │
│   RDS slow   │   │ Agent                                   │  │
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
│              │   │  ```hcl                                  │  │
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
PK: user#{user_id}
SK: session#{session_id}

Attributes:
  session_id: str (UUID)
  user_id: str               # Anonymous UUID stored in browser localStorage until auth is added
  title: str                 # First 80 chars of the user's opening message
  created_at: ISO8601
  updated_at: ISO8601
  status: ACTIVE | CLOSED
  message_count: int
  ttl_expiry: int             # DynamoDB TTL epoch seconds
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
  tool_events: list[ToolEvent] # Persisted Evidence Trail events for UI reload
  tool_result: dict          # If role=TOOL
  tokens_used: int
  created_at: ISO8601
  ttl_expiry: int             # DynamoDB TTL epoch seconds
```

**GSI:** `user-sessions-index` on `user_id` + `created_at` for session listing.

### 6.2 User Identity (Pre-Auth)

Until Okta SSO is integrated, `user_id` is a random UUID generated on first visit and stored in browser `localStorage`. Each browser instance gets its own isolated session namespace. When Okta is added, the UUID is replaced by the Okta `sub` claim with no schema changes required.

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
│   ├── networking/           # Data-only lookups on existing VPC/subnets/SGs
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
      { name = "AWS_REGION",               value = var.aws_region },
      { name = "DYNAMODB_TABLE_SESSIONS",  value = aws_dynamodb_table.sessions.name },
      { name = "DYNAMODB_TABLE_MESSAGES",  value = aws_dynamodb_table.messages.name },
      { name = "BEDROCK_MODEL_ID",         value = "anthropic.claude-sonnet-4-20250514-v1:0" },
      { name = "MAX_TOOL_ITERATIONS",      value = "15" },
      { name = "LLM_PROVIDER",             value = "bedrock" },
      { name = "USE_VPC_ENDPOINTS",        value = tostring(var.use_vpc_endpoints) }
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
        # EC2 / VPC / Networking
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
        # SSM Parameter Store (plaintext only — no SecureString values)
        "ssm:DescribeParameters",
        "ssm:GetParametersByPath",
        # Resource Groups Tagging (cross-service discovery)
        "tag:GetResources", "tag:GetTagKeys", "tag:GetTagValues",
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

**VPC endpoint strategy:** The `use_vpc_endpoints` variable controls whether the agent routes AWS API calls through VPC interface endpoints. Set to `false` if endpoints don't exist and NAT/internet access is available instead. The agent works correctly either way.

```
Internet → CloudFront (SPA) → S3
Internet → API Gateway (HTTP API) → VPC Link → ALB → ECS Fargate (existing private subnet)

ECS Fargate (private) → [VPC Endpoint if use_vpc_endpoints=true] → Bedrock
ECS Fargate (private) → [VPC Endpoint if use_vpc_endpoints=true] → DynamoDB
ECS Fargate (private) → [VPC Endpoint if use_vpc_endpoints=true] → CloudWatch / ECR / SSM
```

**Required Terraform input variables:**

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

variable "use_vpc_endpoints" {
  description = "Route AWS API calls through VPC interface endpoints. Set false if endpoints don't exist and NAT/internet is available."
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
│   │   ├── ec2.py                    # 4.4  — EC2 + VPC + Subnets + SGs + ASG
│   │   ├── rds.py                    # 4.5  — RDS / Aurora PostgreSQL
│   │   ├── dynamodb.py               # 4.6  — DynamoDB
│   │   ├── s3.py                     # 4.7  — S3 + bucket policies
│   │   ├── sqs.py                    # 4.8  — SQS + DLQ
│   │   ├── sns.py                    # 4.9  — SNS
│   │   ├── elb.py                    # 4.10 — ALB / NLB
│   │   ├── apigw.py                  # 4.11 — API Gateway
│   │   ├── cloudfront.py             # 4.12 — CloudFront
│   │   ├── lambda_.py                # 4.13 — Lambda
│   │   ├── stepfunctions.py          # 4.14 — Step Functions (4 tools)
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
│   │   ├── ssm.py                    # 4.25 — SSM Parameter Store (no SecureString values)
│   │   └── tagging.py                # 4.26 — Resource Groups Tagging API
│   │
│   ├── memory/
│   │   └── session_manager.py        # DynamoDB sessions, messages, tool evidence
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
    user_id: str
    messages: list[BaseMessage]          # Full conversation history
    tool_calls_made: int                  # Guard against infinite loops
    clarification_rounds: int             # Max 2
    investigation_plan: str               # LLM-generated plan text
    findings: list[Finding]               # Accumulated evidence
    final_diagnosis: Optional[Diagnosis]
    error: Optional[str]
```

---

## 9. Local Development (Docker Compose + LocalStack)

### 9.1 Overview

**Current implementation note:** local development uses `LLM_PROVIDER=openai` by default. Set `MOCK_AWS=true` for a fully local fake AWS triage scenario, or set `MOCK_AWS=false` plus read-only AWS credentials to inspect a real AWS account. Deployed AWS environments set `LLM_PROVIDER=bedrock`.

Developers run the full stack locally using Docker Compose. LocalStack emulates the app's DynamoDB session/message tables; target AWS tool responses come from built-in mock fixtures or real AWS APIs depending on `MOCK_AWS`.

```
docker compose up
  → triage-agent (FastAPI, port 8000)
  → localstack    (DynamoDB, port 4566)
  → ui-dev        (Vite dev server, port 5173)
```

### 9.2 docker-compose.yml (Local Dev)

```yaml
version: "3.9"

services:
  localstack:
    image: localstack/localstack:3
    ports:
      - "4566:4566"
    environment:
      SERVICES: dynamodb
      DEFAULT_REGION: us-east-1
    volumes:
      - localstack_data:/var/lib/localstack

  agent:
    build:
      context: ./agent-service
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      AWS_REGION: us-east-1
      DYNAMODB_TABLE_SESSIONS: triage-sessions
      DYNAMODB_TABLE_MESSAGES: triage-messages
      BEDROCK_MODEL_ID: anthropic.claude-sonnet-4-20250514-v1:0
      MAX_TOOL_ITERATIONS: "15"
      LLM_PROVIDER: openai
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      OPENAI_MODEL: ${OPENAI_MODEL:-gpt-4o}
      MOCK_AWS: ${MOCK_AWS:-true}
      CORS_ALLOW_ORIGINS: http://localhost:5173
      # Point DynamoDB to LocalStack; triage tools use mock data or real AWS based on MOCK_AWS.
      DYNAMODB_ENDPOINT_URL: http://localstack:4566
      # Optional real AWS creds for read-only triage access when MOCK_AWS=false.
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}
      AWS_SESSION_TOKEN: ${AWS_SESSION_TOKEN:-}
    depends_on:
      - localstack
    volumes:
      - ./agent-service:/app   # Hot-reload in dev

  ui:
    build:
      context: ./ui
      dockerfile: Dockerfile.dev
    ports:
      - "5173:5173"
    environment:
      VITE_API_URL: http://localhost:8000
    volumes:
      - ./ui:/app
      - /app/node_modules

volumes:
  localstack_data:
```

### 9.3 Local DynamoDB Table Creation

The application creates LocalStack DynamoDB tables automatically when `DYNAMODB_ENDPOINT_URL` is configured. The legacy `scripts/bootstrap-local.sh` script can still be used manually for troubleshooting or one-off table recreation:

```bash
#!/usr/bin/env bash
# Creates DynamoDB tables in LocalStack for local development
ENDPOINT=http://localhost:4566

aws dynamodb create-table \
  --endpoint-url $ENDPOINT \
  --table-name triage-sessions \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
    AttributeName=user_id,AttributeType=S \
    AttributeName=created_at,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes '[{
    "IndexName":"user-sessions-index",
    "KeySchema":[{"AttributeName":"user_id","KeyType":"HASH"},{"AttributeName":"created_at","KeyType":"RANGE"}],
    "Projection":{"ProjectionType":"ALL"}
  }]' \
  --region us-east-1

aws dynamodb create-table \
  --endpoint-url $ENDPOINT \
  --table-name triage-messages \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### 9.4 .env.local Template

```bash
# Copy to .env.local — never commit this file
# Local defaults
LLM_PROVIDER=openai
MOCK_AWS=true
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o
CORS_ALLOW_ORIGINS=http://localhost:5173

# Required only when MOCK_AWS=false and local tools should query a real AWS account.
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=        # Optional — for assumed roles / SSO sessions
```

### 9.5 What LocalStack Covers vs Real AWS

Current implementation note: LocalStack covers the app's DynamoDB tables. Local LLM calls use OpenAI, not Bedrock. AWS triage tools use built-in fake data when `MOCK_AWS=true`; otherwise they call real AWS APIs with read-only credentials.

| Concern | LocalStack (local) | Real AWS (target env) |
|---------|-------------------|----------------------|
| DynamoDB session tables | ✅ Emulated | ✅ Real |
| LLM calls | OpenAI via `LLM_PROVIDER=openai` | Bedrock via `LLM_PROVIDER=bedrock` |
| CloudWatch / ECS / RDS tools | Built-in fake data with `MOCK_AWS=true`, or real AWS with read-only creds | ✅ Real |
| Tool unit tests | Mock boto3 responses with `moto` | N/A |

For running the agent without real AWS (e.g. pure CI unit tests), use `moto` to mock individual boto3 calls in the tool layer.

---

## 10. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| Agent modifying resources | IAM role has zero write/mutate permissions. No `Create*`, `Update*`, `Delete*`, `Put*` (except DynamoDB own tables) |
| Prompt injection via log data | Tool outputs are always injected as `tool` role messages, never as `user` messages. System prompt instructs model to treat tool data as untrusted |
| Sensitive data in logs | SSM `GetParametersByPath` only returns plaintext parameters; SecureString values are redacted. Secrets Manager values are never fetched |
| API abuse | API Gateway rate limiting (100 req/s per IP) |
| Authentication | Open in v1 (anonymous UUID per browser). Okta SSO via Cognito SAML in a future phase |
| Container escape | Fargate provides VM-level isolation; no access to underlying host |
| Data exfiltration | Agent runs in private subnet; no outbound internet except via controlled VPC endpoints or NAT |

---

## 11. Authentication

**v1 (current):** No authentication. Each browser generates a random UUID on first visit (stored in `localStorage`) which scopes that browser's sessions. The API has no auth middleware.

**Future phase:** Okta SSO via Amazon Cognito (User Pool acting as SAML SP, Okta as IdP). When added:
- Users authenticate via Cognito Hosted UI → Okta → SAML assertion
- JWT token (Cognito) attached to every API request
- API Gateway Cognito authorizer validates token
- `user_id` switches from localStorage UUID to Okta `sub` claim
- No DynamoDB schema changes required

---

## 12. Observability

| Signal | Tooling |
|--------|---------|
| Agent service logs | CloudWatch Logs (`/ecs/triage-agent`) |
| Distributed traces | AWS X-Ray (LangChain instrumented) |
| Tool call latency | Custom CloudWatch metrics per tool name |
| Token usage | CloudWatch metrics: `InputTokens`, `OutputTokens` per session |
| Error rate | CloudWatch alarm: `5xx` from API Gateway |
| ECS health | CloudWatch Container Insights |

---

## 13. Deployment Flow

GitHub Actions workflows are assumed to **already exist** in the repository. The agent project needs to provide:

1. **`Dockerfile`** — in `agent-service/` (multi-stage build, non-root user)
2. **Terraform modules** — in `terraform/` (Sections 7.1–7.4)
3. **`ui/`** — React SPA build output uploaded to S3

The existing GitHub Actions workflow is expected to:
```
git push → GitHub Actions
  → docker build + push to ECR
  → terraform plan (on PR)
  → terraform apply (on merge to main)
  → ECS rolling deploy (new task def revision)
  → CloudFront invalidation (SPA assets)
```

---

## 14. Configuration Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `bedrock` | `openai` for local dev, `bedrock` for AWS deployment |
| `AWS_REGION` | `us-east-1` | AWS region |
| `BEDROCK_MODEL_ID` | `anthropic.claude-sonnet-4-20250514-v1:0` | Bedrock model |
| `OPENAI_API_KEY` | `""` | Required when `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model used for local development |
| `MOCK_AWS` | `false` | Return fake AWS tool data for local testing without AWS credentials |
| `MAX_TOOL_ITERATIONS` | `15` | Max tool calls per agent loop |
| `MAX_CLARIFICATION_ROUNDS` | `2` | Max rounds of clarification before proceeding |
| `SESSION_TTL_DAYS` | `30` | DynamoDB TTL for sessions |
| `STREAM_TIMEOUT_SECONDS` | `300` | Max SSE connection duration |
| `LOG_QUERY_MAX_RECORDS` | `1000` | Max records per CW Logs Insights query |
| `CORS_ALLOW_ORIGINS` | `*` | Comma-separated FastAPI CORS allow-list |
| `DYNAMODB_ENDPOINT_URL` | `""` | Override DynamoDB endpoint (set to LocalStack URL in local dev) |
| `USE_VPC_ENDPOINTS` | `true` | Route AWS calls through VPC endpoints in deployed env |

---

## 15. Out of Scope (v1)

- **Write remediation actions** — agent recommends only; no automated apply
- **Authentication / SSO** — deferred to a future phase (Okta via Cognito SAML)
- **Multi-account** — single AWS account only in v1; cross-account assumeRole pattern deferred
- **Slack/PagerDuty integration** — chat UI only in v1
- **Scheduled / alert-triggered triage** — user-initiated only in v1
- **Cost anomaly detection** — Cost Explorer APIs not included in v1
- **Vector search over log history** — full-text semantic search across past sessions deferred

---

## 16. Open Questions / Decisions Needed

| # | Question | Status |
|---|----------|--------|
| 1 | Auth provider | Deferred — Okta SSO via Cognito SAML in a future phase |
| 2 | SSE vs WebSocket | **Decided: SSE** — sufficient for streaming; no bidirectional need |
| 3 | VPC: new vs existing | **Decided: inject into existing VPC** via input variables |
| 4 | Multi-env (dev/prod) | Separate Terraform workspaces with `environments/dev` and `environments/prod` tfvars |
| 5 | Log retention | **Decided: 30 days** default, configurable via `SESSION_TTL_DAYS` |
| 6 | User management | **Decided: admin-provisioned** (internal tool); self-service deferred with auth phase |

---

*End of Specification v1.1.0*
