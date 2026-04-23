# Copyright (c) Microsoft. All rights reserved.

"""DevUI single-agent for interactive IaC operations.

Exposes the same tools as the multi-agent workflow (main.py) in a
conversational UI on http://localhost:8090.
"""

from agent_framework import Agent
from agent_framework_devui import serve

import config
from tools.azure_devops_tools import AzureDevOpsTools
from tools.terraform_tools import TerraformTools


def main() -> None:
    credential = config.foundry_credential()

    ado_tools = AzureDevOpsTools(
        organization=config.ado_org(),
        auth_token=config.ado_pat_b64(),
        default_project=config.ado_project(),
    )
    terraform_tools = TerraformTools()

    instructions = config.load_prompt("ado_agent")

    project = config.ado_project()
    if project:
        instructions += f" Default project: '{project}'."
    else:
        instructions += " Ask the user for the project when needed."

    agent = Agent(
        client=config.default_client(credential),
        name="IaCDeploymentAgent",
        instructions=instructions,
        tools=[
            config.build_mcp_tool(),
            ado_tools.create_file_in_repo,
            ado_tools.push_terraform_branch,
            ado_tools.create_pull_request,
            terraform_tools.validate_terraform,
            terraform_tools.format_terraform,
        ],
    )

    serve(entities=[agent], port=8090, auto_open=True)


if __name__ == "__main__":
    main()
