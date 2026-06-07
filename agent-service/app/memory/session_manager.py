import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key

from app.config import settings


class SessionManager:
    """Manages triage sessions and messages in DynamoDB."""

    def __init__(self) -> None:
        kwargs: dict = {"region_name": settings.aws_region}
        if settings.dynamodb_endpoint_url:
            kwargs["endpoint_url"] = settings.dynamodb_endpoint_url

        self._dynamodb = boto3.resource("dynamodb", **kwargs)
        if settings.dynamodb_endpoint_url:
            self._ensure_tables()
        self._sessions_table = self._dynamodb.Table(settings.dynamodb_table_sessions)
        self._messages_table = self._dynamodb.Table(settings.dynamodb_table_messages)

    def _ensure_tables(self) -> None:
        """Create local DynamoDB tables if they don't exist.

        Production tables are managed by Terraform. This path is for LocalStack
        only, where the endpoint URL is explicitly configured.
        """
        client = self._dynamodb.meta.client

        # ── triage-sessions ───────────────────────────────────────────────────
        try:
            client.create_table(
                TableName=settings.dynamodb_table_sessions,
                AttributeDefinitions=[
                    {"AttributeName": "PK", "AttributeType": "S"},
                    {"AttributeName": "SK", "AttributeType": "S"},
                    {"AttributeName": "user_id", "AttributeType": "S"},
                    {"AttributeName": "created_at", "AttributeType": "S"},
                ],
                KeySchema=[
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "user-sessions-index",
                        "KeySchema": [
                            {"AttributeName": "user_id", "KeyType": "HASH"},
                            {"AttributeName": "created_at", "KeyType": "RANGE"},
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                    }
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            # Enable TTL
            client.update_time_to_live(
                TableName=settings.dynamodb_table_sessions,
                TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl_expiry"},
            )
        except client.exceptions.ResourceInUseException:
            pass  # Table already exists — nothing to do

        # ── triage-messages ───────────────────────────────────────────────────
        try:
            client.create_table(
                TableName=settings.dynamodb_table_messages,
                AttributeDefinitions=[
                    {"AttributeName": "PK", "AttributeType": "S"},
                    {"AttributeName": "SK", "AttributeType": "S"},
                ],
                KeySchema=[
                    {"AttributeName": "PK", "KeyType": "HASH"},
                    {"AttributeName": "SK", "KeyType": "RANGE"},
                ],
                BillingMode="PAY_PER_REQUEST",
            )
            client.update_time_to_live(
                TableName=settings.dynamodb_table_messages,
                TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl_expiry"},
            )
        except client.exceptions.ResourceInUseException:
            pass  # Table already exists — nothing to do

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _ttl(self) -> int:
        expiry = datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days)
        return int(expiry.timestamp())

    def create_session(self, user_id: str, session_id: str, title: str) -> dict:
        """Create a new triage session."""
        now = self._now_iso()
        item = {
            "PK": f"user#{user_id}",
            "SK": f"session#{session_id}",
            "session_id": session_id,
            "user_id": user_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
            "status": "active",
            "message_count": 0,
            "ttl_expiry": self._ttl(),
        }
        self._sessions_table.put_item(Item=item)
        return item

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session by session_id via scan with filter (small table, acceptable cost)."""
        from boto3.dynamodb.conditions import Attr
        response = self._sessions_table.scan(
            FilterExpression=Attr("session_id").eq(session_id),
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return None
        return self._format_session(items[0])

    def list_sessions(self, user_id: str) -> list[dict]:
        """List all sessions for a user via GSI user-sessions-index."""
        response = self._sessions_table.query(
            KeyConditionExpression=Key("PK").eq(f"user#{user_id}"),
        )
        items = response.get("Items", [])
        return [self._format_session(i) for i in sorted(items, key=lambda x: x.get("created_at", ""), reverse=True)]

    def delete_session(self, session_id: str) -> None:
        """Delete a session. Finds and deletes by session_id."""
        session = self.get_session(session_id)
        if not session:
            return
        self._sessions_table.delete_item(
            Key={
                "PK": f"user#{session['user_id']}",
                "SK": f"session#{session_id}",
            }
        )

    def _format_session(self, item: dict) -> dict:
        return {
            "session_id": item.get("session_id", ""),
            "user_id": item.get("user_id", ""),
            "title": item.get("title", ""),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "status": item.get("status", "active"),
            "message_count": int(item.get("message_count", 0)),
        }

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: Optional[list] = None,
        tool_events: Optional[list] = None,
        tool_result: Optional[dict] = None,
        tokens_used: Optional[int] = None,
    ) -> dict:
        """Save a message to the triage-messages table."""
        now = self._now_iso()
        message_id = str(uuid.uuid4())
        item: dict = {
            "PK": f"session#{session_id}",
            "SK": f"msg#{now}#{message_id}",
            "message_id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "created_at": now,
            "ttl_expiry": self._ttl(),
        }
        if tool_calls is not None:
            item["tool_calls"] = tool_calls
        if tool_events is not None:
            item["tool_events"] = tool_events
        if tool_result is not None:
            item["tool_result"] = tool_result
        if tokens_used is not None:
            item["tokens_used"] = tokens_used

        self._messages_table.put_item(Item=item)

        # Update message count and updated_at on session
        # Best-effort — ignore errors
        try:
            session = self.get_session(session_id)
            if session:
                self._sessions_table.update_item(
                    Key={
                        "PK": f"user#{session['user_id']}",
                        "SK": f"session#{session_id}",
                    },
                    UpdateExpression="SET updated_at = :ua ADD message_count :inc",
                    ExpressionAttributeValues={":ua": now, ":inc": 1},
                )
        except Exception:
            pass

        return item

    def get_messages(self, session_id: str) -> list[dict]:
        """Get all messages for a session, sorted by SK (chronological)."""
        response = self._messages_table.query(
            KeyConditionExpression=Key("PK").eq(f"session#{session_id}"),
        )
        items = response.get("Items", [])
        sorted_items = sorted(items, key=lambda x: x.get("SK", ""))
        return [self._format_message(i) for i in sorted_items]

    def _format_message(self, item: dict) -> dict:
        return {
            "message_id": item.get("message_id", ""),
            "session_id": item.get("session_id", ""),
            "role": item.get("role", "USER"),
            "content": item.get("content", ""),
            "tool_calls": item.get("tool_calls"),
            "tool_events": item.get("tool_events"),
            "tool_result": item.get("tool_result"),
            "tokens_used": item.get("tokens_used"),
            "created_at": item.get("created_at", ""),
        }

    def delete_messages(self, session_id: str) -> None:
        """Delete all messages for a session via scan + batch delete."""
        response = self._messages_table.query(
            KeyConditionExpression=Key("PK").eq(f"session#{session_id}"),
            ProjectionExpression="PK, SK",
        )
        items = response.get("Items", [])
        with self._messages_table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
