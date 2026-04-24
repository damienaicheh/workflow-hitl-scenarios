import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import AzureCliCredential


def _create_foundry_client() -> FoundryChatClient:
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_DEFAULT_MODEL"],
        credential=AzureCliCredential(),
    )


def register_publisher_agent(
    project_client: AIProjectClient,
    repo: str,
    project: str,
) -> str:

    instructions = f"""
        You are a publisher agent. Do not ask for confirmation.
        The Azure DevOps project is '{project}' and the repository is '{repo}'.
        You do not modify Terraform. You only choose the branch name,
        pull request title, and pull request description for publication.
        Do not claim that a branch or pull request already exists.
        The executor will perform the publication after your response.
    """

    publisher_agent = project_client.agents.create_version(
        agent_name="PublisherAgent",
        definition=PromptAgentDefinition(
            model=os.environ["FOUNDRY_DEFAULT_MODEL"],
            instructions=instructions.strip(),
        ),
    )

    return publisher_agent.name


def build_publisher_agent(agent_name: str) -> Agent:
    return Agent(
        client=_create_foundry_client(),
        name=agent_name,
    )
