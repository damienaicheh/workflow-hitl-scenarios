import os

from agent_framework import Agent
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from utils.env import create_foundry_client


def create_publisher_agent(
    project_client: AIProjectClient,
) -> Agent:
    ado_project = os.environ["ADO_DEFAULT_PROJECT"]
    repository = os.environ["ADO_REPO"]

    instructions = f"""
        You are a publisher agent. Do not ask for confirmation.
        The Azure DevOps project is '{ado_project}' and the repository is '{repository}'.
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

    return Agent(
        client=create_foundry_client(),
        name=publisher_agent.name,
    )
