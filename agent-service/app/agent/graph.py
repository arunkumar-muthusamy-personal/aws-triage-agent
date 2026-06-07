from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage
from langchain_core.language_models import BaseChatModel

from app.agent.state import AgentState
from app.agent.nodes import format_system_message
from app.config import settings
from app.tools import ALL_TOOLS


def _build_llm() -> BaseChatModel:
    """Return the configured LLM — Bedrock in production, OpenAI for local dev."""
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI  # imported lazily — not installed in prod
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            streaming=True,
        )
    else:
        from langchain_aws import ChatBedrockConverse
        return ChatBedrockConverse(
            model=settings.bedrock_model_id,
            region_name=settings.aws_region,
            streaming=True,
        )


llm = _build_llm()
llm_with_tools = llm.bind_tools(ALL_TOOLS)


async def agent_node(state: AgentState) -> dict:
    """Call the LLM with the current message history."""
    messages = state["messages"]
    response: AIMessage = await llm_with_tools.ainvoke(messages)

    tool_calls_made = state.get("tool_calls_made", 0)
    # Count new tool calls
    if hasattr(response, "tool_calls") and response.tool_calls:
        tool_calls_made += len(response.tool_calls)

    return {
        "messages": [response],
        "tool_calls_made": tool_calls_made,
    }


def should_continue(state: AgentState) -> str:
    """Determine whether to call tools or end."""
    messages = state["messages"]
    last_message = messages[-1]

    tool_calls_made = state.get("tool_calls_made", 0)

    # If last message has tool calls and we haven't hit the limit, go to tools
    if (
        hasattr(last_message, "tool_calls")
        and last_message.tool_calls
        and tool_calls_made < settings.max_tool_iterations
    ):
        return "tools"

    return END


# Build graph
workflow = StateGraph(AgentState)

workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(ALL_TOOLS))

workflow.set_entry_point("agent")

workflow.add_conditional_edges(
    "agent",
    should_continue,
    {"tools": "tools", END: END},
)

workflow.add_edge("tools", "agent")

graph = workflow.compile()
