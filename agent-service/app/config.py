from typing import Literal, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── LLM provider ──────────────────────────────────────────────────────────
    # "bedrock"  → AWS Bedrock (production)
    # "openai"   → OpenAI API (local dev / testing)
    llm_provider: Literal["bedrock", "openai"] = "bedrock"

    # Bedrock settings (used when llm_provider=bedrock)
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-sonnet-4-20250514-v1:0"

    # OpenAI settings (used when llm_provider=openai)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o"

    # ── Agent behaviour ────────────────────────────────────────────────────────
    max_tool_iterations: int = 15
    max_clarification_rounds: int = 2
    session_ttl_days: int = 30
    stream_timeout_seconds: int = 300
    log_query_max_records: int = 1000
    cors_allow_origins: str = "*"

    # ── Mock mode (local dev without real AWS creds) ──────────────────────────
    # When True, all AWS triage tools return realistic fake data.
    # DynamoDB (sessions/messages) still uses LocalStack as normal.
    mock_aws: bool = False

    # ── DynamoDB ───────────────────────────────────────────────────────────────
    dynamodb_table_sessions: str = "triage-sessions"
    dynamodb_table_messages: str = "triage-messages"
    dynamodb_endpoint_url: Optional[str] = None  # set to LocalStack URL in local dev

    use_vpc_endpoints: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
