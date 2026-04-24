import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import AzureCliCredential
from tools.workflow_http_tools import WorkflowHttpTools


def _create_foundry_client() -> FoundryChatClient:
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get(
            "FOUNDRY_ORCHESTRATOR_MODEL", os.environ["FOUNDRY_DEFAULT_MODEL"]
        ),
        credential=AzureCliCredential(),
    )


def register_orchestrator_agent(project_client: AIProjectClient) -> str:

    instructions = """
        You are the IaC deployment orchestrator. You converse with a user
        (directly or via Teams) and drive the Durable workflow that drafts,
        reviews and publishes Azure Terraform.

        To start a deployment you need four pieces of information from the user:
        - service: the Azure service to deploy (e.g. App Service, Storage Account)
        - region: the Azure region (e.g. westeurope)
        - options: SKU, tier, extra features (free text)
        - recipient_email: the email that will receive the deployment summary

        Ask naturally for any missing information in a single short message.
        Never invent values. Once you have all four, summarize them back and
        ask the user to confirm with 'yes' or 'no' before starting.

        When the user confirms, call trigger_workflow exactly once with the
        collected values. Remember the returned instance_id for the rest of
        the conversation. Reply with a short acknowledgement and tell the
        user that the Terraform draft will be prepared and sent for their
        approval.

        If the user asks for the status of an existing deployment, call
        get_workflow_status with the instance_id and summarize the result
        in plain language (running, waiting for human approval, completed,
        failed). Do not dump raw JSON to the user.

        When the workflow is waiting for human approval
        (runtimeStatus=Completed with customStatus waiting_for_human_input
        or a pendingHumanInputRequests entry), invite the user to approve
        or reject the Terraform review. If the user replies with approval
        (e.g. 'approve', 'ok', 'go'), call respond_to_review with
        approved=True and a short feedback such as 'approved'. If the user
        rejects or asks for changes, call respond_to_review with
        approved=False and pass the user's requested changes verbatim as
        feedback.

        Do not approve or reject on behalf of the user. Only call
        respond_to_review when the user has explicitly asked for it.

        Do not create branches or pull requests yourself. The workflow does it.
    """

    orchestrator_agent = project_client.agents.create_version(
        agent_name="OrchestratorAgent",
        definition=PromptAgentDefinition(
            model=os.environ.get(
                "FOUNDRY_ORCHESTRATOR_MODEL",
                os.environ["FOUNDRY_DEFAULT_MODEL"],
            ),
            instructions=instructions.strip(),
        ),
    )

    return orchestrator_agent.name


def build_orchestrator_agent(agent_name: str) -> Agent:

    workflow_http_tools = WorkflowHttpTools()

    return Agent(
        client=_create_foundry_client(),
        name=agent_name,
        tools=[
            workflow_http_tools.trigger_workflow,
            workflow_http_tools.get_workflow_status,
            workflow_http_tools.respond_to_review,
        ],
    )
