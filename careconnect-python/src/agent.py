import json
import os
import sys

from iris_llm import Agent, Provider, get_default_model
from iris_llm.utils import get_api_key

from tools import SDoHPythonTools

IRIS_MCP_URL = os.environ.get(
    "IRIS_MCP_URL",
    "http://iris:52773/mcp/careconnect",
)

SYSTEM_PROMPT = (
    "You are a CareConnect community health worker assistant. "
    "You help CHWs assess patients for social determinants of health (SDoH) risk "
    "and connect them with appropriate community resources.\n\n"
    "You have access to:\n"
    "- Python-based SDoH tools: assess_sdoh_risk, fetch_community_resources, summarize_sdoh_findings\n"
    "- IRIS ObjectScript tools: SearchPatients, FetchPatientSummary, GetInteropTraces\n\n"
    "For a complete patient assessment:\n"
    "1. Use SearchPatients to find the patient\n"
    "2. Use FetchPatientSummary to get their clinical data\n"
    "3. Use assess_sdoh_risk to score all five SDoH domains\n"
    "4. Use fetch_community_resources with their zip code if available\n"
    "5. Use summarize_sdoh_findings to produce the CHW action brief"
)


def build_agent() -> Agent:
    api_key, provider_name = get_api_key()
    if not api_key:
        print("ERROR: Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or BEDROCK_ACCESS_KEY")
        sys.exit(1)

    provider = Provider(provider_name, json.dumps({"api_key": api_key}))
    agent = Agent.with_provider(get_default_model(provider_name), provider)
    agent.system_prompt = SYSTEM_PROMPT

    agent.add_tool(SDoHPythonTools())

    agent.add_tool({
        "type": "mcp:remote",
        "url": IRIS_MCP_URL,
        "auth": {
            "type": "basic",
            "username": os.environ.get("IRIS_USERNAME", "_SYSTEM"),
            "password": os.environ.get("IRIS_PASSWORD", "SYS"),
        },
    })

    return agent


def main():
    agent = build_agent()

    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"\nPrompt: {prompt}\n")
        response = agent.run(prompt)
        print(f"Response:\n{response}")
        return

    print("CareConnect SDoH Agent (iris_llm Python)")
    print("Type 'quit' to exit\n")
    while True:
        try:
            prompt = input("CHW> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if prompt.lower() in ("quit", "exit", "q"):
            break
        if not prompt:
            continue
        response = agent.run(prompt)
        print(f"\n{response}\n")


if __name__ == "__main__":
    main()
