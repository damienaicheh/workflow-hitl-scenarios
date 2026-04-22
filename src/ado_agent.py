import argparse
import asyncio
import base64
import os

from agent_framework import Agent, MCPStdioTool
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv(override=False)


def get_first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def require_env(*names: str) -> str:
    value = get_first_env(*names)
    if value:
        return value
    joined_names = ", ".join(names)
    raise ValueError(
        f"Missing required environment variable. Set one of: {joined_names}"
    )


def resolve_ado_org() -> str:
    return require_env("ADO_ORG").removeprefix("https://dev.azure.com/").strip("/")


def resolve_pat_credential() -> str:
    raw_pat = get_first_env("ADO_PAT")
    if not raw_pat:
        raise ValueError("PAT auth requires ADO_PAT.")

    # Azure DevOps only uses the PAT portion of username:pat, so any non-empty placeholder works.
    pat_identity = "ado@example.invalid"
    return base64.b64encode(f"{pat_identity}:{raw_pat}".encode("utf-8")).decode("utf-8")


def resolve_ado_domains() -> list[str]:
    raw_domains = get_first_env("ADO_DOMAINS")
    if not raw_domains:
        return []

    return [domain.strip() for domain in raw_domains.split(",") if domain.strip()]


def build_ado_mcp_tool() -> MCPStdioTool:
    tool_args = [
        "-y",
        "@azure-devops/mcp",
        resolve_ado_org(),
        "--authentication",
        "pat",
    ]

    for domain in resolve_ado_domains():
        tool_args.extend(["-d", domain])

    return MCPStdioTool(
        name="azure_devops",
        command="npx",
        args=tool_args,
        env={"PERSONAL_ACCESS_TOKEN": resolve_pat_credential()},
        load_prompts=False,
        approval_mode="never_require",
        description="Azure DevOps tools exposed through the local Azure DevOps MCP server.",
    )


async def run_query(query: str) -> str:
    credential = DefaultAzureCredential()

    async with Agent(
        client=FoundryChatClient(
            project_endpoint=require_env("FOUNDRY_PROJECT_ENDPOINT"),
            model=require_env("FOUNDRY_DEFAULT_MODEL"),
            credential=credential,
        ),
        name="AzureDevOpsAgent",
        instructions=f"""
            You are an Azure DevOps assistant.
            Use Azure DevOps MCP tools when they help answer the user.",
            Ask for missing project, repository, pull request, or work item context before making changes.",
            When the user does not specify a project, start with the Azure DevOps project '{get_first_env("ADO_DEFAULT_PROJECT")}'."
        """,
        tools=build_ado_mcp_tool(),
    ) as agent:
        print("Agent: ", end="", flush=True)
        stream = agent.run(query, stream=True)
        chunks: list[str] = []

        async for chunk in stream:
            if chunk.text:
                print(chunk.text, end="", flush=True)
                chunks.append(chunk.text)

        final_response = await stream.get_final_response()

    final_text = (final_response.text or "".join(chunks)).strip() or str(final_response)
    if not chunks and final_text:
        print(final_text, end="", flush=True)

    print()
    return final_text


async def main() -> None:
    await run_query("List all projects in my Azure DevOps organization.")


if __name__ == "__main__":
    asyncio.run(main())
