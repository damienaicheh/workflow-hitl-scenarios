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


def register_reviewer_agent(project_client: AIProjectClient) -> str:

    instructions = """
        You are an IaC reviewer. 
        Run validate_terraform and format_terraform on the Terraform files made by the Terraform Drafter agent.
        If validation fails, describe the errors.
        If it passes, output the formatted files as the same JSON list.
    """

    reviewer_agent = project_client.agents.create_version(
        agent_name="ReviewerAgent",
        definition=PromptAgentDefinition(
            model=os.environ["FOUNDRY_DEFAULT_MODEL"],
            instructions=instructions.strip(),
        ),
    )

    return reviewer_agent.name


def build_reviewer_agent(agent_name: str) -> Agent:

    terraform_tools = TerraformTools()

    return Agent(
        client=_create_foundry_client(),
        name=agent_name,
        tools=[
            terraform_tools.validate_terraform,
            terraform_tools.format_terraform,
        ],
    )
