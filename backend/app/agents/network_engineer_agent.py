"""
NetworkEngineerAgent — LangGraph ReAct agent com network engineering persona.

Phase 3-4: Agent com tools RAG. O agent decide quando buscar documentacao
antes de responder, seguindo o padrao ReAct (Reason → Act → Observe).
"""
from __future__ import annotations

import time
from typing import AsyncGenerator
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

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

Available Tools:
- search_rag_global: Search vendor documentation (Cisco, Juniper, Arista). Use for protocol \
configuration, troubleshooting, best practices, and vendor-specific features.
- search_rag_local: Search the user's uploaded documents. Use when the user refers to their \
own network, configs, or uploaded files.
- parse_config: Parse a network device configuration into structured data. Use when the user \
pastes a config and wants it analyzed or explained. Auto-detects Cisco/Juniper.
- validate_config: Validate a config against security, reliability, and performance best \
practices. Use when the user asks to review, audit, or validate a configuration.
- parse_show_commands: Parse the output of Cisco show commands into structured tables. Use \
when the user pastes terminal output from show commands.
- analyze_pcap: Analyze an uploaded PCAP file. Auto-detects wired vs wireless captures. \
For Ethernet/IP: protocol distribution, top talkers with bytes, anomalies, TCP issues, \
bandwidth/throughput (avg+peak), frame size distribution, time-series traffic buckets, \
HTTP deep analysis (methods, status codes, URLs, hosts), TLS/SSL analysis (versions, SNI, \
cipher suites, handshakes), VoIP/SIP detection (SIP methods/responses, RTP streams/codecs). \
For 802.11 Wi-Fi: frame types, deauth/disassoc events with reason codes, retry rate, \
signal strength (dBm), channels, SSIDs, bandwidth stats, wireless anomaly detection. \
Use when the user asks about a packet capture they uploaded.

Guidelines:
- Always provide accurate, vendor-specific commands when possible.
- When uncertain, say so clearly instead of guessing.
- Include relevant show/debug commands to help verify configurations.
- Consider security best practices in every recommendation.
- Use structured formatting (code blocks for configs, tables for comparisons).
- Answer in the same language the user writes in.
- Use your available tools proactively: search documentation before answering technical \
questions, parse configs when the user pastes one, validate when asked to review.
- When the user pastes a configuration, use parse_config to understand it. If they also ask \
for validation, use validate_config as well.
- When the user pastes show command output, use parse_show_commands to structure the data.
- If a tool search returns no results, answer based on your training knowledge but mention \
that no specific documentation was found.
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


def _build_graph(chat_model, tools: list[BaseTool] | None = None) -> StateGraph:
    """
    Build the LangGraph state graph.

    Sem tools: START → agent → END
    Com tools: START → agent → should_continue → tool_node → agent (loop)
                                               → END
    """

    if tools:
        chat_model = chat_model.bind_tools(tools)

    async def agent_node(state: AgentState) -> dict:
        response = await chat_model.ainvoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.set_entry_point("agent")

    if tools:
        tool_node = ToolNode(tools)
        graph.add_node("tools", tool_node)

        def should_continue(state: AgentState) -> str:
            last_message = state["messages"][-1]
            if isinstance(last_message, AIMessage) and last_message.tool_calls:
                return "tools"
            return END

        graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge("agent", END)

    return graph


class NetworkEngineerAgent:
    """
    LangGraph-based network engineering agent com suporte a tools.

    Args:
        provider_name: LLM provider (openai, anthropic, azure).
        api_key: Plaintext API key.
        model: Optional model name override.
        tools: Optional list of LangChain tools para o agent usar.
    """

    def __init__(
        self,
        provider_name: str,
        api_key: str,
        model: str | None = None,
        tools: list[BaseTool] | None = None,
    ) -> None:
        self._chat_model = _create_chat_model(provider_name, api_key, model)
        self._tools = tools
        graph = _build_graph(self._chat_model, tools)
        self._compiled = graph.compile()
        self._recursion_limit = settings.AGENT_MAX_ITERATIONS * 2 + 1

    async def stream_response(
        self,
        messages: list[dict],
    ) -> AsyncGenerator[dict, None]:
        """
        Stream the agent response com suporte a tool calls.

        Args:
            messages: Conversation history as list of
                      {"role": str, "content": str} dicts.

        Yields:
            Dicts com tipo:
            - {"type": "text", "content": "..."}
            - {"type": "tool_call_start", "tool_call_id": "...", "tool_name": "...", "tool_input": "..."}
            - {"type": "tool_call_end", "tool_call_id": "...", "tool_name": "...", "result_preview": "...", "duration_ms": ...}
        """
        lc_messages = [SystemMessage(content=NETWORK_ENGINEER_SYSTEM_PROMPT)]
        for msg in messages:
            if msg["role"] == "user":
                lc_messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_messages.append(AIMessage(content=msg["content"]))
            elif msg["role"] == "system":
                lc_messages.append(SystemMessage(content=msg["content"]))

        tool_start_times: dict[str, float] = {}
        tool_ids_by_name: dict[str, list[str]] = {}

        async for event in self._compiled.astream_events(
            {"messages": lc_messages},
            version="v2",
            config={"recursion_limit": self._recursion_limit},
        ):
            kind = event.get("event")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and isinstance(chunk, AIMessage):
                    if chunk.content and isinstance(chunk.content, str):
                        yield {"type": "text", "content": chunk.content}

            elif kind == "on_tool_start":
                tool_name = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", {})
                raw_tool_call_id = event.get("run_id")
                tool_call_id = str(raw_tool_call_id) if raw_tool_call_id else str(uuid4())
                tool_start_times[tool_call_id] = time.time()
                tool_ids_by_name.setdefault(tool_name, []).append(tool_call_id)
                input_str = tool_input if isinstance(tool_input, str) else str(tool_input)
                yield {
                    "type": "tool_call_start",
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_input": input_str[:500],
                }

            elif kind == "on_tool_end":
                tool_name = event.get("name", "unknown")
                output = event.get("data", {}).get("output", "")
                result_str = str(output) if not isinstance(output, str) else output
                raw_tool_call_id = event.get("run_id")
                tool_call_id = str(raw_tool_call_id) if raw_tool_call_id else ""
                if tool_call_id and tool_call_id not in tool_start_times:
                    tool_call_id = ""
                if not tool_call_id:
                    ids_for_name = tool_ids_by_name.get(tool_name, [])
                    tool_call_id = ids_for_name.pop(0) if ids_for_name else str(uuid4())

                start = tool_start_times.pop(tool_call_id, None)
                duration_ms = int((time.time() - start) * 1000) if start else 0
                yield {
                    "type": "tool_call_end",
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "result_preview": result_str[:300],
                    "duration_ms": duration_ms,
                    "full_result": result_str,
                }
