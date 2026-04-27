import logging
import os
from pathlib import Path

from agent_framework import Workflow, WorkflowBuilder
from agent_framework_azurefunctions import AgentFunctionApp
from agents.publisher import create_publisher_agent
from agents.reviewer import create_reviewer_agent
from agents.summary_email import create_summary_email_agent
from agents.terraform_drafter import create_terraform_drafter_agent
from azure.ai.projects import AIProjectClient
from dotenv import load_dotenv
from executors.drafter_executor import DrafterExecutor
from executors.input_router_executor import InputRouterExecutor
from executors.reviewer_executor import ReviewerExecutor
from executors.summary_executor import SummaryExecutor
from utils.env import create_azure_credential

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


def create_workflow() -> Workflow:
    credential = create_azure_credential()

    project = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=credential,
    )

    drafter_agent = create_terraform_drafter_agent(project)
    reviewer_agent = create_reviewer_agent(project)
    publisher_agent = create_publisher_agent(project)
    summary_agent = create_summary_email_agent(project)

    input_router = InputRouterExecutor()
    drafter_executor = DrafterExecutor(drafter_agent)
    reviewer_executor = ReviewerExecutor(reviewer_agent, drafter_agent, publisher_agent)
    summary_executor = SummaryExecutor(summary_agent)

    return (
        WorkflowBuilder(start_executor=input_router)
        .add_edge(input_router, drafter_executor)
        .add_edge(drafter_executor, reviewer_executor)
        .add_edge(reviewer_executor, summary_executor)
        .build()
    )


def create_app() -> AgentFunctionApp:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    workflow = create_workflow()

    return AgentFunctionApp(workflow=workflow, enable_health_check=True)


app = create_app()
