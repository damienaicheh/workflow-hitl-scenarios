import os

from agent_framework import Agent
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from tools.terraform_tools import TerraformTools
from utils.env import create_foundry_client


def create_reviewer_agent(project_client: AIProjectClient) -> Agent:
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

    terraform_tools = TerraformTools()

    return Agent(
        client=create_foundry_client(),
        name=reviewer_agent.name,
        tools=[
            terraform_tools.validate_terraform,
            terraform_tools.format_terraform,
        ],
    )
