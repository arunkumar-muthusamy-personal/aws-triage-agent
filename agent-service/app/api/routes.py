import json
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter
from langchain_core.messages import AIMessage, HumanMessage
from sse_starlette import EventSourceResponse

from app.agent.graph import graph
from app.agent.nodes import format_system_message
from app.api.schemas import ChatRequest, MessageRecord, SessionSummary
from app.memory.session_manager import SessionManager

router = APIRouter()
session_manager = SessionManager()


def _json_safe(value):
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return str(value)


def _coerce_tool_output(raw_output):
    output = raw_output.content if hasattr(raw_output, "content") else raw_output
    if isinstance(output, str):
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output
    return _json_safe(output)


async def stream_agent(request: ChatRequest, session_id: str) -> AsyncGenerator[dict, None]:
    try:
        stored_messages = session_manager.get_messages(session_id)

        messages = [format_system_message()]
        for msg in stored_messages:
            if msg["role"] == "USER":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "ASSISTANT":
                messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=request.message))
        session_manager.save_message(
            session_id=session_id,
            role="USER",
            content=request.message,
        )

        state_input = {
            "session_id": session_id,
            "user_id": request.user_id,
            "messages": messages,
            "tool_calls_made": 0,
            "clarification_rounds": 0,
            "investigation_plan": "",
            "findings": [],
            "final_diagnosis": None,
            "error": None,
        }

        config = {"configurable": {"thread_id": session_id}}
        full_response_parts = []
        tool_events = []
        tool_started_at = {}

        async for event in graph.astream_events(state_input, config=config, version="v2"):
            kind = event.get("event")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    token = chunk.content if isinstance(chunk.content, str) else ""
                    if token:
                        full_response_parts.append(token)
                        yield {"event": "token", "data": json.dumps({"token": token})}

            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                run_id = event.get("run_id") or str(uuid.uuid4())
                tool_input = _json_safe(event.get("data", {}).get("input", {}))
                tool_started_at[run_id] = time.monotonic()
                tool_events.append(
                    {
                        "type": "tool_start",
                        "tool": tool_name,
                        "input": tool_input,
                    }
                )
                yield {
                    "event": "tool_start",
                    "data": json.dumps({"tool": tool_name, "input": tool_input}),
                }

            elif kind == "on_tool_end":
                tool_name = event.get("name", "unknown")
                run_id = event.get("run_id")
                output = _coerce_tool_output(event.get("data", {}).get("output"))
                started_at = tool_started_at.pop(run_id, None) if run_id else None
                duration_ms = int((time.monotonic() - started_at) * 1000) if started_at else None
                tool_events.append(
                    {
                        "type": "tool_end",
                        "tool": tool_name,
                        "output": output,
                        "duration_ms": duration_ms,
                    }
                )
                yield {
                    "event": "tool_end",
                    "data": json.dumps(
                        {"tool": tool_name, "output": output, "duration_ms": duration_ms},
                        default=str,
                    ),
                }

        full_response = "".join(full_response_parts)
        session_manager.save_message(
            session_id=session_id,
            role="ASSISTANT",
            content=full_response,
            tool_events=tool_events,
        )
        yield {"event": "done", "data": json.dumps({"session_id": session_id})}

    except Exception as e:
        yield {"event": "error", "data": json.dumps({"error": str(e)})}


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())

    existing = session_manager.get_session(session_id)
    if not existing:
        title = request.message[:80]
        session_manager.create_session(
            user_id=request.user_id,
            session_id=session_id,
            title=title,
        )

    return EventSourceResponse(stream_agent(request, session_id))


@router.get("/sessions")
async def list_sessions(user_id: str) -> list[SessionSummary]:
    sessions = session_manager.list_sessions(user_id)
    return [SessionSummary(**s) for s in sessions]


@router.get("/sessions/{session_id}")
async def get_session_messages(session_id: str) -> list[MessageRecord]:
    messages = session_manager.get_messages(session_id)
    return [MessageRecord(**m) for m in messages]


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    session_manager.delete_session(session_id)
    session_manager.delete_messages(session_id)
    return {"deleted": session_id}
