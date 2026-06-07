# AWS Triage Agent

A conversational AI agent for diagnosing production incidents in AWS. Describe a problem in plain English — the agent autonomously queries CloudWatch Logs, AWS service APIs, and correlates signals across 26 services to produce a structured diagnosis.

See [SPEC.md](./SPEC.md) for the full architecture and design spec.

---

## Quick Start (Local Dev)

### Prerequisites
- Docker + Docker Compose
- AWS credentials with **read-only** access to the target AWS account + Bedrock `InvokeModel` permission
- AWS CLI (for the bootstrap script)

### 1. Configure credentials

```bash
cp .env.local.example .env.local
# Edit .env.local and fill in your AWS credentials
```

### 2. Start the stack

```bash
docker compose up --build
```

This starts:
- **LocalStack** on port 4566 (DynamoDB for session storage)
- **Agent service** (FastAPI) on port 8000
- **UI** (Vite dev server) on port 5173

### 3. Create DynamoDB tables in LocalStack

In a separate terminal (run once after `docker compose up`):

```bash
chmod +x scripts/bootstrap-local.sh
./scripts/bootstrap-local.sh
```

### 4. Open the UI

Visit http://localhost:5173

---

## Project Structure

```
aws-triage-agent/
├── agent-service/          # Python FastAPI + LangGraph backend
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── agent/          # LangGraph graph, nodes, state, prompts
│       ├── api/            # FastAPI routes + Pydantic schemas
│       ├── memory/         # DynamoDB session manager
│       └── tools/          # 26 read-only AWS tool modules (62 tools)
│
├── ui/                     # React + TypeScript frontend
│   ├── src/
│   │   ├── components/     # ChatMessage, EvidenceTrail, SessionSidebar
│   │   ├── hooks/          # useSSEChat, useSessions, useUserId
│   │   └── types/
│   └── Dockerfile.dev
│
├── terraform/              # Infrastructure as code
│   ├── modules/            # ecr, dynamodb, iam, networking, ecs, api_gateway, frontend
│   └── environments/       # dev/ and prod/ tfvars
│
├── scripts/
│   └── bootstrap-local.sh  # Creates DynamoDB tables in LocalStack
│
├── docker-compose.yml
└── .env.local.example
```

---

## AWS Credentials for Local Dev

The agent needs two types of AWS access:

| Access | Why |
|--------|-----|
| `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` | Calling Claude via Bedrock |
| Read-only on all monitored services | Running triage tools (see SPEC.md §7.3 for the full IAM policy) |

The simplest approach: use a read-only IAM role in the target account and assume it locally via `AWS_SESSION_TOKEN`. The Bedrock call also needs to be in `us-east-1`.

---

## Deploying to AWS

### Prerequisites
- Terraform >= 1.5
- An existing VPC with private and public subnets
- Bedrock access to `anthropic.claude-sonnet-4-20250514-v1:0` enabled in `us-east-1`

### 1. Push the Docker image to ECR

After running `terraform apply` once to create the ECR repo:

```bash
# Get the ECR URL from Terraform output
ECR_URL=$(terraform -chdir=terraform output -raw ecr_repository_url)

aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_URL

docker build -t $ECR_URL:latest ./agent-service
docker push $ECR_URL:latest
```

### 2. Apply Terraform

```bash
cd terraform

# For dev environment
terraform init
terraform apply -var-file=environments/dev/terraform.tfvars \
  -var="vpc_id=vpc-xxxxxxxx" \
  -var='private_subnet_ids=["subnet-aaa","subnet-bbb"]' \
  -var='public_subnet_ids=["subnet-ccc","subnet-ddd"]'
```

### 3. Deploy the UI

```bash
cd ui
npm install
npm run build

# Upload dist/ to the S3 bucket (output from Terraform)
S3_BUCKET=$(terraform -chdir=../terraform output -raw s3_bucket_name)
aws s3 sync dist/ s3://$S3_BUCKET --delete

# Invalidate CloudFront cache
CF_ID=$(terraform -chdir=../terraform output -raw cloudfront_distribution_id)
aws cloudfront create-invalidation --distribution-id $CF_ID --paths "/*"
```

---

## Agent Tools

The agent has 62 read-only tools across 26 AWS services. All tools:
- Instantiate boto3 clients per-call (no globals)
- Handle `ClientError` gracefully
- Never fetch secret values (SSM SecureStrings are redacted, Secrets Manager values are never requested)

See [SPEC.md §4](./SPEC.md#4-tool-registry) for the full tool catalogue.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region |
| `BEDROCK_MODEL_ID` | `anthropic.claude-sonnet-4-20250514-v1:0` | Bedrock model |
| `MAX_TOOL_ITERATIONS` | `15` | Max tool calls per agent loop |
| `DYNAMODB_TABLE_SESSIONS` | `triage-sessions` | Session table name |
| `DYNAMODB_TABLE_MESSAGES` | `triage-messages` | Messages table name |
| `DYNAMODB_ENDPOINT_URL` | _(empty)_ | Override DynamoDB endpoint (set to `http://localstack:4566` in Docker Compose) |
