from langchain_core.messages import SystemMessage
from app.agent.prompts import SYSTEM_PROMPT


def format_system_message() -> SystemMessage:
    """Return the system prompt as a LangChain SystemMessage."""
    return SystemMessage(content=SYSTEM_PROMPT)
