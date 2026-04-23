"""Shared configuration for the IaC Deployment Assistant."""

from __future__ import annotations

import base64
import logging
import os

from agent_framework import MCPStdioTool
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv(override=False)

log = logging.getLogger(__name__)

# ── Environment helpers ──────────────────────────────────────────────


def get_env(*names: str) -> str | None:
    """Return the first non-empty value among *names*, or ``None``."""
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def require_env(*names: str) -> str:
    """Like :func:`get_env` but raises if nothing is set."""
    value = get_env(*names)
    if value:
        return value
    raise ValueError(
        f"Missing required env var. Set one of: {', '.join(names)}"
    )


# ── Azure DevOps ─────────────────────────────────────────────────────


def ado_org() -> str:
    return require_env("ADO_ORG").removeprefix("https://dev.azure.com/").strip("/")


def ado_project() -> str | None:
    return get_env("ADO_DEFAULT_PROJECT")


def ado_repo() -> str:
    """Repository name — defaults to the project name if not set."""
    return get_env("ADO_REPO") or require_env("ADO_DEFAULT_PROJECT")


def ado_pat_b64() -> str:
    """Base-64 encoded ``user:PAT`` for Azure DevOps REST API auth."""
    raw = get_env("ADO_PAT")
    if not raw:
        raise ValueError("ADO_PAT is required for Azure DevOps operations.")
    return base64.b64encode(f"ado@agent:{raw}".encode()).decode()


def ado_domains() -> list[str]:
    raw = get_env("ADO_DOMAINS")
    if not raw:
        return []
    return [d.strip() for d in raw.split(",") if d.strip()]


def build_mcp_tool() -> MCPStdioTool:
    """Build the Azure DevOps MCP stdio tool."""
    args = ["-y", "@azure-devops/mcp", ado_org(), "--authentication", "pat"]
    for domain in ado_domains():
        args.extend(["-d", domain])

    return MCPStdioTool(
        name="azure_devops",
        command="npx",
        args=args,
        env={"PERSONAL_ACCESS_TOKEN": ado_pat_b64()},
        load_prompts=False,
        approval_mode="never_require",
        description="Azure DevOps MCP tools (repos, pipelines, work items).",
    )


# ── Foundry clients ─────────────────────────────────────────────────


def foundry_credential() -> AzureCliCredential:
    return AzureCliCredential()


def default_client(credential: AzureCliCredential | None = None) -> FoundryChatClient:
    cred = credential or foundry_credential()
    return FoundryChatClient(
        project_endpoint=require_env("FOUNDRY_PROJECT_ENDPOINT"),
        model=require_env("FOUNDRY_DEFAULT_MODEL"),
        credential=cred,
    )


def orchestrator_client(
    credential: AzureCliCredential | None = None,
) -> FoundryChatClient:
    """Return the orchestrator client, falling back to :func:`default_client`."""
    model = get_env("FOUNDRY_ORCHESTRATOR_MODEL")
    if not model:
        return default_client(credential)
    cred = credential or foundry_credential()
    return FoundryChatClient(
        project_endpoint=require_env("FOUNDRY_PROJECT_ENDPOINT"),
        model=model,
        credential=cred,
    )
