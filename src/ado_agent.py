# Copyright (c) Microsoft. All rights reserved.

"""DevUI single-agent for interactive IaC operations.

Exposes the same tools as the multi-agent workflow (main.py) in a
conversational UI on http://localhost:8090.
"""

from agent_framework import Agent
from agent_framework_devui import serve

import config
from tools.azure_devops_tools import AzureDevOpsTools
from tools.pipeline_tools import PipelineTools
from tools.teams_tools import TeamsTools
from tools.terraform_tools import TerraformTools


def main() -> None:
    credential = config.foundry_credential()

    ado_tools = AzureDevOpsTools(
        organization=config.ado_org(),
        auth_token=config.ado_pat_b64(),
        default_project=config.ado_project(),
    )
    terraform_tools = TerraformTools()
    pipeline_tools = PipelineTools(
        organization=config.ado_org(),
        auth_token=config.ado_pat_b64(),
        default_project=config.ado_project(),
    )

    webhook = config.get_env("TEAMS_WEBHOOK_URL")
    teams_tools = TeamsTools(webhook_url=webhook) if webhook else None

    instructions = [
        "You are an IaC Deployment Assistant for Azure DevOps.",
        "You can generate, validate, format, and push Terraform code.",
        "Use Azure DevOps MCP tools when they help answer the user.",
        "Use push_terraform_branch to push files to a new branch.",
        "Use create_pull_request to create PRs after pushing code.",
        "Use validate_terraform and format_terraform before pushing.",
        "Use get_pipeline_runs and get_pipeline_run_status to monitor pipelines.",
    ]

    project = config.ado_project()
    if project:
        instructions.append(f"Default project: '{project}'.")
    else:
        instructions.append("Ask the user for the project when needed.")

    if teams_tools:
        instructions.append("Use send_teams_approval_card to notify Teams channels.")

    all_tools = [
        config.build_mcp_tool(),
        ado_tools.create_file_in_repo,
        ado_tools.push_terraform_branch,
        ado_tools.create_pull_request,
        terraform_tools.validate_terraform,
        terraform_tools.format_terraform,
        pipeline_tools.get_pipeline_runs,
        pipeline_tools.get_pipeline_run_status,
    ]
    if teams_tools:
        all_tools.append(teams_tools.send_teams_approval_card)
        all_tools.append(teams_tools.send_teams_status_card)

    agent = Agent(
        client=config.default_client(credential),
        name="IaCDeploymentAgent",
        instructions=" ".join(instructions),
        tools=all_tools,
    )

    serve(entities=[agent], port=8090, auto_open=True)


if __name__ == "__main__":
    main()
