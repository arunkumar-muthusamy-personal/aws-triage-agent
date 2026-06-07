from datetime import datetime, timezone

from langchain_core.messages import SystemMessage
from app.agent.prompts import SYSTEM_PROMPT


def format_system_message() -> SystemMessage:
    """Return the system prompt as a LangChain SystemMessage."""
    now_utc = datetime.now(timezone.utc).isoformat()
    runtime_context = f"""

RUNTIME CONTEXT:
- Current time is {now_utc}.
- Treat relative time windows like "last 1 hour" or "last 30 minutes" as UTC windows ending at the current time above.
- When calling AWS tools with start_time/end_time, use ISO 8601 timestamps with timezone offsets, preferably UTC.
- CloudWatch Logs and CloudWatch Metrics timestamps are UTC; do not use local browser or workstation time unless the user explicitly gives a timezone.
"""
    return SystemMessage(content=SYSTEM_PROMPT + runtime_context)
