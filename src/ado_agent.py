import base64
import os

from agent_framework import Agent, MCPStdioTool
from agent_framework.foundry import FoundryChatClient
from agent_framework_devui import serve
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from tools.azure_devops_tools import AzureDevOpsTools
from tools.terraform_tools import TerraformTools

load_dotenv(override=False)


# ── Environment helpers ──────────────────────────────────────────────

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


# ── Main ─────────────────────────────────────────────────────────────

def main():
    credential = DefaultAzureCredential()
    default_project = get_first_env("ADO_DEFAULT_PROJECT")

    ado_tools = AzureDevOpsTools(
        organization=resolve_ado_org(),
        auth_token=resolve_pat_credential(),
        default_project=default_project,
    )
    terraform_tools = TerraformTools()

    instructions = [
        "You are an IaC Deployment Assistant for Azure DevOps.",
        "You can generate Terraform code, validate it, format it, and push it to Azure DevOps repositories.",
        "Use Azure DevOps MCP tools when they help answer the user.",
        "Use create_file_in_repo to add or update files in a repository.",
        "Use push_terraform_branch to push multiple Terraform files to a new branch.",
        "Use create_pull_request to create PRs after pushing code.",
        "Use validate_terraform and format_terraform to check Terraform code before pushing.",
        "Ask for missing project, repository, branch, or file path context before making changes.",
    ]
    if default_project:
        instructions.append(
            f"When the user does not specify a project, use '{default_project}'."
        )
    else:
        instructions.append(
            "Ask the user for the Azure DevOps project when it is not provided."
        )

    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=require_env("FOUNDRY_PROJECT_ENDPOINT"),
            model=require_env("FOUNDRY_DEFAULT_MODEL"),
            credential=credential,
        ),
        name="IaCDeploymentAgent",
        instructions=" ".join(instructions),
        tools=[
            build_ado_mcp_tool(),
            ado_tools.create_file_in_repo,
            ado_tools.push_terraform_branch,
            ado_tools.create_pull_request,
            terraform_tools.validate_terraform,
            terraform_tools.format_terraform,
        ],
    )

    serve(
        entities=[agent],
        port=8090,
        auto_open=True,
    )


if __name__ == "__main__":
    main()
