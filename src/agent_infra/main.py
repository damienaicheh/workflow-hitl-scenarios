import os

from agent_framework._agents import Agent
from agent_framework_foundry import FoundryChatClient
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from tools.workflow_http_tools import WorkflowHttpTools

load_dotenv()


def main():
    credential = AzureCliCredential()
    project_client = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=credential,
    )

    instructions = """
        You are the IaC deployment orchestrator. You converse with a user
        (directly or via Teams) and drive the Durable workflow that drafts,
        reviews and publishes Azure Terraform.

        To start a deployment you need four pieces of information from the user:
        - service: the Azure service to deploy (e.g. App Service, Storage Account)
        - region: the Azure region (e.g. westeurope)
        - options: SKU, tier, extra features (free text)

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
        agent_name="InfraOrchestratorAgent",
        definition=PromptAgentDefinition(
            model=os.environ["FOUNDRY_ORCHESTRATOR_MODEL"],
            instructions=instructions.strip(),
        ),
    )

    workflow_http_tools = WorkflowHttpTools()

    orchestrator_agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_ORCHESTRATOR_MODEL"],
            credential=AzureCliCredential(),
        ),
        name=orchestrator_agent.name,
        tools=[
            workflow_http_tools.trigger_workflow,
            workflow_http_tools.get_workflow_status,
            workflow_http_tools.respond_to_review,
        ],
    )


if __name__ == "__main__":
    main()
