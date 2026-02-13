"""
NetworkEngineerAgent — LangGraph-based agent with network engineering persona.

Phase 1-2: LLM-only (no tools). The graph structure supports adding tool
nodes in Phase 3-4 without refactoring.
"""
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.core.config import settings

NETWORK_ENGINEER_SYSTEM_PROMPT = """\
You are NetGuru, an expert AI network engineer assistant.

Your specialties include:
- Cisco IOS/IOS-XE/NX-OS, Juniper Junos, Arista EOS configuration and troubleshooting
- Routing protocols (OSPF, BGP, EIGRP, IS-IS) design and debugging
- Switching (VLANs, STP, VxLAN, EVPN) architecture
- Network security (ACLs, firewalls, VPNs, 802.1X)
- PCAP/packet analysis and protocol diagnosis
- Network automation (Ansible, Python/Netmiko/NAPALM)
- Cloud networking (AWS VPC, Azure VNet, GCP)

Guidelines:
- Always provide accurate, vendor-specific commands when possible.
- When uncertain, say so clearly instead of guessing.
- Include relevant show/debug commands to help verify configurations.
- Consider security best practices in every recommendation.
- Use structured formatting (code blocks for configs, tables for comparisons).
- Answer in the same language the user writes in.
"""


def _create_chat_model(
    provider_name: str,
    api_key: str,
    model: str | None = None,
):
    """
    Create a LangChain chat model based on the provider.

    Returns:
        A LangChain ChatModel instance (ChatOpenAI, ChatAnthropic, or AzureChatOpenAI).
    """
    provider_name = provider_name.lower().strip()

    if provider_name == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=api_key,
            model=model or settings.DEFAULT_LLM_MODEL_OPENAI,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            streaming=True,
        )

    if provider_name == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            api_key=api_key,
            model_name=model or settings.DEFAULT_LLM_MODEL_ANTHROPIC,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            streaming=True,
        )

    if provider_name == "azure":
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            api_key=api_key,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version="2024-02-01",
            model=model or settings.DEFAULT_LLM_MODEL_AZURE,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            streaming=True,
        )

    raise ValueError(f"Unsupported provider: {provider_name}")


def _build_graph(chat_model) -> StateGraph:
    """
    Build the LangGraph state graph.

    Current structure (Phase 1-2):
        START -> agent -> END

    Future structure (Phase 3-4):
        START -> agent -> should_use_tool? -> tool_node -> agent
                                           -> END
    """

    async def agent_node(state: AgentState) -> dict:
        response = await chat_model.ainvoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)

    return graph


class NetworkEngineerAgent:
    """
    LangGraph-based network engineering agent.

    Args:
        provider_name: LLM provider (openai, anthropic, azure).
        api_key: Plaintext API key.
        model: Optional model name override.
    """

    def __init__(
        self,
        provider_name: str,
        api_key: str,
        model: str | None = None,
    ) -> None:
        self._chat_model = _create_chat_model(provider_name, api_key, model)
        graph = _build_graph(self._chat_model)
        self._compiled = graph.compile()

    async def stream_response(
        self,
        messages: list[dict],
    ) -> AsyncGenerator[str, None]:
        """
        Stream the agent response token-by-token.

        Args:
            messages: Conversation history as list of
                      {"role": str, "content": str} dicts.

        Yields:
            Text chunks as they are produced by the LLM.
        """
        # Convert plain dicts to LangChain message objects
        lc_messages = [SystemMessage(content=NETWORK_ENGINEER_SYSTEM_PROMPT)]
        for msg in messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                from langchain_core.messages import AIMessage

                lc_messages.append(AIMessage(content=msg["content"]))
            elif msg["role"] == "system":
                lc_messages.append(SystemMessage(content=msg["content"]))

        async for event in self._compiled.astream_events(
            {"messages": lc_messages},
            version="v2",
        ):
            kind = event.get("event")
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield chunk.content
