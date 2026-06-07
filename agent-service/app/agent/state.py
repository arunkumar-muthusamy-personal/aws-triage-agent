from typing import TypedDict, Optional, Annotated
from langchain_core.messages import BaseMessage
import operator


class Finding(TypedDict):
    tool: str
    summary: str
    raw: dict


class Diagnosis(TypedDict):
    root_cause: str
    evidence: list[str]
    recommended_fix: str
    prevention: Optional[str]


class AgentState(TypedDict):
    session_id: str
    user_id: str
    messages: Annotated[list[BaseMessage], operator.add]
    tool_calls_made: int
    clarification_rounds: int
    investigation_plan: str
    findings: list[Finding]
    final_diagnosis: Optional[Diagnosis]
    error: Optional[str]
