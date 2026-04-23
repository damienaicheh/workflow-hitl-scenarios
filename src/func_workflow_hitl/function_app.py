import base64
import logging
import os
import sys
from pathlib import Path

from agent_framework import Agent, Workflow, WorkflowBuilder
from agent_framework.foundry import FoundryChatClient
from agent_framework_azurefunctions import AgentFunctionApp
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from executors.drafter_executor import DrafterExecutor
from executors.reviewer_executor import ReviewerExecutor
from executors.finalizer_executor import PublisherExecutor
from executors.input_router_executor import InputRouterExecutor
from tools.azure_devops_tools import AzureDevOpsTools
from azure.ai.projects import AIProjectClient
from agents.terraform_drafter import create_terraform_drafter_agent
from agents.reviewer import create_reviewer_agent

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


def create_workflow() -> Workflow:
    credential = AzureCliCredential()
    
    project = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=credential,
    )
    
    foundry_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_DEFAULT_MODEL"],
        credential=AzureCliCredential(),
    )


    terraform_drafter = create_terraform_drafter_agent(project, foundry_client)

    reviewer = create_reviewer_agent(project, foundry_client)


    repo = os.environ.get("ADO_REPO", "ai-scenarios")
    publisher = Agent(
        client=foundry_client,
        name="publisher",
        instructions=(
            "You are a Git operations specialist. Push the validated Terraform "
            f"files to the repository '{repo}' using push_terraform_branch. "
            "Then create a Pull Request using create_pull_request. "
            "Output the PR URL."
        ),
    )

    input_router = InputRouterExecutor()
    drafter_executor = DrafterExecutor(terraform_drafter)
    reviewer_executor = ReviewerExecutor(reviewer, terraform_drafter)
    publisher_executor = PublisherExecutor(publisher)

    return (
        WorkflowBuilder(start_executor=input_router)
        .add_edge(input_router, drafter_executor)
        .add_edge(drafter_executor, reviewer_executor)
        .add_edge(reviewer_executor, publisher_executor)
        .build()
    )


def create_app() -> AgentFunctionApp:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    workflow = create_workflow()
    return AgentFunctionApp(workflow=workflow, enable_health_check=True)


app = create_app()
