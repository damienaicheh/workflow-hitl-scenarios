import os

from agent_framework import Agent
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from tools.terraform_tools import TerraformTools
from utils.env import create_foundry_client


def create_terraform_drafter_agent(project_client: AIProjectClient) -> Agent:
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

    terraform_tools = TerraformTools()

    return Agent(
        client=create_foundry_client(),
        name=terraform_drafter.name,
        tools=[
            terraform_tools.validate_terraform,
            terraform_tools.format_terraform,
        ],
    )
