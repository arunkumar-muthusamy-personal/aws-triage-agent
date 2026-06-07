import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from sse_starlette import EventSourceResponse

from app.api.schemas import ChatRequest, SessionSummary, MessageRecord
from app.memory.session_manager import SessionManager
from app.agent.graph import graph
from app.agent.nodes import format_system_message
from langchain_core.messages import HumanMessage

router = APIRouter()
session_manager = SessionManager()


async def stream_agent(request: ChatRequest, session_id: str) -> AsyncGenerator[dict, None]:
    try:
        # Load message history
        stored_messages = session_manager.get_messages(session_id)

        # Build message list
        messages = [format_system_message()]
        for msg in stored_messages:
            if msg["role"] == "USER":
                messages.append(HumanMessage(content=msg["content"]))
            # ASSISTANT and TOOL messages are managed by LangGraph checkpointer internally

        messages.append(HumanMessage(content=request.message))

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
                tool_input = event.get("data", {}).get("input", {})
                # tool_input may contain non-serialisable objects — coerce safely
                try:
                    input_serialisable = json.loads(json.dumps(tool_input, default=str))
                except Exception:
                    input_serialisable = str(tool_input)
                yield {
                    "event": "tool_start",
                    "data": json.dumps({"tool": tool_name, "input": input_serialisable}),
                }

            elif kind == "on_tool_end":
                tool_name = event.get("name", "unknown")
                raw_output = event.get("data", {}).get("output")
                # In LangGraph v2 events, tool output is a ToolMessage object
                if hasattr(raw_output, "content"):
                    output_str = raw_output.content
                elif isinstance(raw_output, str):
                    output_str = raw_output
                else:
                    try:
                        output_str = json.dumps(raw_output, default=str)
                    except Exception:
                        output_str = str(raw_output)
                yield {
                    "event": "tool_end",
                    "data": json.dumps({"tool": tool_name, "output": output_str}),
                }

        full_response = "".join(full_response_parts)
        session_manager.save_message(
            session_id=session_id,
            role="ASSISTANT",
            content=full_response,
        )
        yield {"event": "done", "data": json.dumps({"session_id": session_id})}

    except Exception as e:
        yield {"event": "error", "data": json.dumps({"error": str(e)})}


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())

    # Create session if new
    existing = session_manager.get_session(session_id)
    if not existing:
        title = request.message[:80]
        session_manager.create_session(
            user_id=request.user_id,
            session_id=session_id,
            title=title,
        )

    # Save user message
    session_manager.save_message(
        session_id=session_id,
        role="USER",
        content=request.message,
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
