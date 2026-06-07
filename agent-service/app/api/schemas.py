from typing import Optional, Literal
from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    user_id: str
    message: str


class SessionSummary(BaseModel):
    session_id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str
    status: str
    message_count: int


class MessageRecord(BaseModel):
    message_id: str
    session_id: str
    role: Literal["USER", "ASSISTANT", "TOOL"]
    content: str
    tool_calls: Optional[list] = None
    tool_events: Optional[list] = None
    tool_result: Optional[dict] = None
    tokens_used: Optional[int] = None
    created_at: str
