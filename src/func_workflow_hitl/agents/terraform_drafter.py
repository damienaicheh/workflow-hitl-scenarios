import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import AzureCliCredential
from tools.terraform_tools import TerraformTools


def _create_foundry_client() -> FoundryChatClient:
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_DEFAULT_MODEL"],
        credential=AzureCliCredential(),
    )


def register_terraform_drafter_agent(project_client: AIProjectClient) -> str:

    instructions = """
        You are an IaC Deployment Assistant for Azure DevOps.
        Generate Terraform files as a JSON list with 'filename' and 'content'.
        Use validate_terraform and format_terraform before returning the files.
        Do not create branches or pull requests.
    """

    terraform_drafter = project_client.agents.create_version(
        agent_name="TerraformDrafterAgent",
        definition=PromptAgentDefinition(
            model=os.environ["FOUNDRY_DEFAULT_MODEL"],
            instructions=instructions.strip(),
        ),
    )

    return terraform_drafter.name


def build_terraform_drafter_agent(agent_name: str) -> Agent:

    terraform_tools = TerraformTools()

    return Agent(
        client=_create_foundry_client(),
        name=agent_name,
        tools=[
            terraform_tools.validate_terraform,
            terraform_tools.format_terraform,
        ],
    )
