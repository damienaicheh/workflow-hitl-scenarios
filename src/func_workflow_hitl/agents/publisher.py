import os

from agent_framework import Agent
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from configs.ado_config import AdoConfig
from tools.azure_devops_tools import AzureDevOpsTools
from utils.env import create_foundry_client


def create_publisher_agent(
    project_client: AIProjectClient, ado_config: AdoConfig
) -> Agent:
    ado_project = ado_config.default_project
    repository = ado_config.repository

    instructions = f"""
        You are a publisher agent. Do not ask for confirmation.
        The Azure DevOps project is '{ado_project}' and the repository is '{repository}'.
        You must publish the approved Terraform bundle yourself and you must not modify its content.
        The available Azure DevOps tools are enough to complete the scenario.
        For this workflow, decide yourself which tools to call to create a source branch,
        publish the Terraform bundle to that branch, and open the pull request.
        Prefer this sequence for a multi-file Terraform bundle: create_branch, push_terraform_branch,
        create_pull_request, then optionally get_pull_request to confirm the created PR metadata.
        create_file_in_repo is available for one-off file operations if you truly need it.
        Generate the source branch name, commit message, pull request title, and pull request description yourself.
        The project and repository are already configured as '{ado_project}' and '{repository}'.
        Prefer omitting repository and project arguments so the tools use their configured defaults.
        If you do provide them, they must be exactly '{repository}' and '{ado_project}'. Never invent another repository.
        Your final answer must be only the PublisherResult object populated from actual successful tool outputs.
        Do not claim that a branch or pull request exists unless the corresponding tool call succeeded.
        If a tool call fails or required publication data is missing, do not fabricate a result.
    """

    publisher_agent = project_client.agents.create_version(
        agent_name="PublisherAgentA",
        definition=PromptAgentDefinition(
            model=os.environ["FOUNDRY_ORCHESTRATOR_MODEL"],
            instructions=instructions.strip(),
        ),
    )

    azure_devops_tools = AzureDevOpsTools(ado_config=ado_config)

    return Agent(
        client=create_foundry_client(with_advanced_model=True),
        name=publisher_agent.name,
        tools=[
            azure_devops_tools.create_branch,
            azure_devops_tools.push_files_to_branch,
            azure_devops_tools.create_pull_request,
            azure_devops_tools.get_pull_request,
            azure_devops_tools.create_file_in_repo,
        ],
    )
