"""
LangGraph agent state definition.
"""
from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """
    State shared across nodes in the agent graph.

    messages: Full conversation history managed by LangGraph's
              add_messages reducer (appends new, deduplicates by id).
    """

    messages: Annotated[list[BaseMessage], add_messages]
