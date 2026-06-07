from datetime import datetime, timezone
from typing import Optional


def parse_aws_datetime(value: Optional[str], default: datetime) -> datetime:
    """Parse an ISO timestamp and default naive values to UTC."""
    if not value:
        return default

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
