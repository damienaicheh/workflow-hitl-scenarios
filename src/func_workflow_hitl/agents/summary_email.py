import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import AzureCliCredential
from tools.email_tools import AcsEmailTools


def _create_foundry_client() -> FoundryChatClient:
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_DEFAULT_MODEL"],
        credential=AzureCliCredential(),
    )


def register_summary_email_agent(project_client: AIProjectClient) -> str:

    instructions = """
        You are a summary and email agent. You receive:
        - the approved Terraform configuration,
        - the Azure DevOps pull request result (branch name, pull request id and URL),
        - the recipient email address.

        Write a concise HTML email summarizing what will be deployed
        (services, region, main options) and include the pull request URL
        so the human can review and approve the deployment.

        Then call send_email exactly once with:
        - recipient: the provided recipient email address,
        - subject: a short subject starting with 'IaC Deployment Ready:',
        - html_body: the HTML email body.

        Do not ask for confirmation.
    """

    summary_agent = project_client.agents.create_version(
        agent_name="SummaryEmailAgent",
        definition=PromptAgentDefinition(
            model=os.environ["FOUNDRY_DEFAULT_MODEL"],
            instructions=instructions.strip(),
        ),
    )

    return summary_agent.name


def build_summary_email_agent(agent_name: str) -> Agent:

    email_tools = AcsEmailTools()

    return Agent(
        client=_create_foundry_client(),
        name=agent_name,
        tools=[email_tools.send_email],
    )
