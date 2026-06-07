#!/usr/bin/env bash
set -euo pipefail

ENDPOINT_URL="http://localhost:4566"
REGION="us-east-1"

# LocalStack accepts any non-empty credentials — export dummies if not already set
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-localstack-dummy}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-localstack-dummy}"
export AWS_DEFAULT_REGION="${REGION}"

echo "Waiting for LocalStack to be ready..."
until curl -sf "${ENDPOINT_URL}/_localstack/health" | grep -q '"dynamodb": "available"'; do
  echo "  LocalStack not ready yet — retrying in 3s..."
  sleep 3
done
echo "LocalStack is ready."

echo "Creating DynamoDB table: triage-sessions..."
aws dynamodb create-table \
  --endpoint-url "${ENDPOINT_URL}" \
  --region "${REGION}" \
  --table-name triage-sessions \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
    AttributeName=user_id,AttributeType=S \
    AttributeName=created_at,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes '[
    {
      "IndexName": "user-sessions-index",
      "KeySchema": [
        {"AttributeName": "user_id", "KeyType": "HASH"},
        {"AttributeName": "created_at", "KeyType": "RANGE"}
      ],
      "Projection": {"ProjectionType": "ALL"}
    }
  ]' \
  --query "TableDescription.TableName" \
  --output text

echo "Enabling TTL on triage-sessions..."
aws dynamodb update-time-to-live \
  --endpoint-url "${ENDPOINT_URL}" \
  --region "${REGION}" \
  --table-name triage-sessions \
  --time-to-live-specification Enabled=true,AttributeName=ttl

echo "Creating DynamoDB table: triage-messages..."
aws dynamodb create-table \
  --endpoint-url "${ENDPOINT_URL}" \
  --region "${REGION}" \
  --table-name triage-messages \
  --attribute-definitions \
    AttributeName=PK,AttributeType=S \
    AttributeName=SK,AttributeType=S \
  --key-schema \
    AttributeName=PK,KeyType=HASH \
    AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --query "TableDescription.TableName" \
  --output text

echo "Enabling TTL on triage-messages..."
aws dynamodb update-time-to-live \
  --endpoint-url "${ENDPOINT_URL}" \
  --region "${REGION}" \
  --table-name triage-messages \
  --time-to-live-specification Enabled=true,AttributeName=ttl

echo "Bootstrap complete. Tables created:"
aws dynamodb list-tables \
  --endpoint-url "${ENDPOINT_URL}" \
  --region "${REGION}" \
  --output table
