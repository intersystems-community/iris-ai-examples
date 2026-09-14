"""
CareConnect — SDoH Patient Snapshot Agent (Python / LangChain)

Mirrors the ObjectScript CareConnect.Agent.SDoHAssessment but from Python,
using langchain-intersystems for LLM + MCP tool access.

Pattern from: ready2026-hackathon/ReadyAI-demo/langchain_external/readyai_app/app/agent/get_patient_snapshot.py
Extends with: phi_guardian routing, IRISVectorStore memory recall, streaming tool visibility

Usage:
    agent = SDoHAgent("chw_user", "chw_pass")
    async for chunk in agent.stream_response("Assess patient Patient/42 for SDoH risk factors"):
        print(chunk, end="", flush=True)
"""

import asyncio
import base64
import json
import os
from typing import AsyncIterator

import iris
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallRequest, wrap_tool_call
from langchain.messages import HumanMessage
from langchain_core.messages import ToolMessage
from langchain_intersystems.chat_models import init_chat_model
from langchain_intersystems import IRISVectorStore
from langchain_mcp_adapters.client import MultiServerMCPClient

from phi_guardian import PhiGuardian

_IRIS_HOST = os.environ.get("IRIS_HUB_HOST", "iris-ai-hub")
_IRIS_PORT = int(os.environ.get("IRIS_HUB_PORT", "1973"))
_IRIS_NS = os.environ.get("IRIS_HUB_NAMESPACE", "USER")
_MCP_URL = os.environ.get("MCP_URL", "http://iris-ai-hub:8888/mcp/careconnect")
_FHIR_HOST = os.environ.get("FHIR_HOST", "iris-fhir")
_FHIR_PORT = int(os.environ.get("FHIR_PORT", "52773"))
_LLM_CONFIG = os.environ.get("LLM_CONFIG_NAME", "openai")
_OLLAMA_CONFIG = os.environ.get("OLLAMA_CONFIG_NAME", "ollama")

SYSTEM_PROMPT = """\
You are a CareConnect SDoH assessment agent helping community health workers (CHWs).

Your workflow for each patient:
1. Call fetch_patient_summary to get clinical data from the FHIR repository
2. Call search_sdoh_protocols to find relevant screening guidelines
3. Call recall_similar_cases to check agent memory for prior similar patients
4. Call assess_sdoh_risk to score the six SDoH domains
5. Call draft_care_plan to produce actionable CHW recommendations
6. Optionally call trigger_follow_up if immediate action is needed

Role-based access:
- Doctors: full access including trigger_follow_up
- Nurses: read-only (fetch, search, assess, draft)
- CHW: all tools via chw_role

Never state a diagnosis. Provide risk scores and recommendations only.
Always cite the source for each finding.
"""


@wrap_tool_call
async def _handle_tool_error(request: ToolCallRequest, handler):
    try:
        return await handler(request)
    except Exception as exc:
        name = request.tool_call.get("name", "unknown_tool")
        tid = request.tool_call.get("id", name)
        return ToolMessage(
            content=f"Tool '{name}' failed: {type(exc).__name__}: {exc}. "
            "Continue without this result and note the limitation.",
            name=name,
            tool_call_id=tid,
            status="error",
        )


class SDoHAgent:
    """
    LangChain-based SDoH assessment agent.

    Uses langchain-intersystems for:
    - LLM via IRIS Config Store (init_chat_model)
    - Vector memory recall via IRISVectorStore
    - MCP tools via MultiServerMCPClient → objectscript-mcp

    Uses phi_guardian for:
    - PHI scan before every LLM call
    - Routing: PHI content → Ollama (local), safe → OpenAI via Config Store
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._guardian = PhiGuardian.from_config("phi_rules.yaml")

    def _conn(self):
        return iris.connect(
            _IRIS_HOST, _IRIS_PORT, _IRIS_NS, self.username, self.password
        )

    def _select_llm(self, query: str, conn):
        scan = self._guardian.scan(query)
        if scan.is_sensitive:
            return init_chat_model(
                _OLLAMA_CONFIG, conn
            ), "ollama (local — PHI detected)"
        return init_chat_model(
            _LLM_CONFIG, conn
        ), f"{_LLM_CONFIG} (via IRIS Config Store)"

    async def _get_tools(self):
        auth = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        client = MultiServerMCPClient(
            {
                "careconnect": {
                    "transport": "http",
                    "url": _MCP_URL,
                    "headers": {"Authorization": f"Basic {auth}"},
                }
            }
        )
        try:
            return await client.get_tools()
        except Exception as e:
            raise RuntimeError(
                f"Failed to retrieve MCP tools from {_MCP_URL}\n"
                f"Is the iris-ai-hub container running? Error: {e}"
            ) from e

    async def _recall_memory(self, query: str, k: int = 3) -> str:
        conn = self._conn()
        try:
            from langchain_openai import OpenAIEmbeddings

            store = IRISVectorStore(
                embedding_function=OpenAIEmbeddings(),
                connect_args=(
                    _IRIS_HOST,
                    _IRIS_PORT,
                    _IRIS_NS,
                    self.username,
                    self.password,
                ),
                collection_name="ai_memory_semantic",
            )
            docs = store.similarity_search(query, k=k)
            if not docs:
                return ""
            return "\n".join(f"- {d.page_content[:200]}" for d in docs)
        except Exception:
            return ""
        finally:
            conn.close()

    async def get_agent(self, query: str = ""):
        conn = self._conn()
        model, routing_note = self._select_llm(query, conn)
        conn.close()

        tools = await self._get_tools()

        system = SYSTEM_PROMPT
        if routing_note:
            system += f"\n\n[LLM routing: {routing_note}]"

        return create_agent(
            model=model,
            tools=tools,
            system_prompt=system,
            middleware=[_handle_tool_error],
        )

    async def stream_response(self, prompt: str) -> AsyncIterator:
        prior_cases = await self._recall_memory(prompt)
        if prior_cases:
            full_prompt = (
                f"{prompt}\n\n"
                f"Context from similar prior cases in agent memory:\n{prior_cases}"
            )
        else:
            full_prompt = prompt

        agent = await self.get_agent(full_prompt)
        seen = {}

        try:
            async for chunk in agent.astream(
                {"messages": [HumanMessage(content=full_prompt)]},
                stream_mode="messages",
            ):
                message, _ = chunk
                if message.type in ("ai", "AIMessageChunk"):
                    for block in getattr(message, "content_blocks", []) or []:
                        if block["type"] == "text":
                            yield block["text"]
                        elif block["type"] == "tool_call":
                            tid = block.get("id") or block.get("name")
                            if tid and tid not in seen:
                                seen[tid] = block.get("name")
                                yield {
                                    "type": "tool_call",
                                    "id": tid,
                                    "name": block.get("name"),
                                    "status": "running",
                                    "args": json.dumps(block.get("args", {}), indent=2),
                                }
                elif message.type == "tool":
                    tid = getattr(message, "tool_call_id", None)
                    name = getattr(message, "name", None) or seen.get(tid)
                    if tid and name:
                        content = getattr(message, "content", "")
                        if isinstance(content, list):
                            content = "\n".join(str(x) for x in content)
                        yield {
                            "type": "tool_result",
                            "id": tid,
                            "name": name,
                            "status": getattr(message, "status", "completed")
                            or "completed",
                            "content": str(content).strip(),
                        }
        except Exception as e:
            yield f"\n\nAgent error: {type(e).__name__}: {e}"


async def main():
    agent = SDoHAgent(
        username=os.environ.get("CHW_USERNAME", "chw_user"),
        password=os.environ.get("CHW_PASSWORD", "chw_pass"),
    )
    async for chunk in agent.stream_response(
        "Assess patient Patient/42 for SDoH risk factors and draft a care plan."
    ):
        if isinstance(chunk, str):
            print(chunk, end="", flush=True)
        elif isinstance(chunk, dict) and chunk["type"] == "tool_call":
            print(f"\n[calling {chunk['name']}...]", flush=True)
        elif isinstance(chunk, dict) and chunk["type"] == "tool_result":
            print(
                f"\n[{chunk['name']} returned {len(chunk['content'])} chars]",
                flush=True,
            )


if __name__ == "__main__":
    asyncio.run(main())
