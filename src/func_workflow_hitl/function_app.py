import json
import logging
import os
import sys
from pathlib import Path

import azure.functions as func
from agent_framework import Agent, AgentSession, Workflow, WorkflowBuilder
from agent_framework_azurefunctions import AgentFunctionApp
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from agents.orchestrator import (
    build_orchestrator_agent,
    register_orchestrator_agent,
)
from agents.publisher import build_publisher_agent, register_publisher_agent
from agents.reviewer import build_reviewer_agent, register_reviewer_agent
from agents.summary_email import (
    build_summary_email_agent,
    register_summary_email_agent,
)
from agents.terraform_drafter import (
    build_terraform_drafter_agent,
    register_terraform_drafter_agent,
)
from azure.ai.projects import AIProjectClient
from executors.drafter_executor import DrafterExecutor
from executors.finalizer_executor import PublisherExecutor
from executors.input_router_executor import InputRouterExecutor
from executors.reviewer_executor import ReviewerExecutor
from executors.summary_executor import SummaryExecutor
from tools.azure_devops_tools import AzureDevOpsTools
from utils.response_format import extract_response_text

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


def create_workflow() -> Workflow:
    credential = AzureCliCredential()

    project = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=credential,
    )

    azure_devops_tools = AzureDevOpsTools(
        organization=os.environ["ADO_ORG"],
        auth_token=os.environ["ADO_PAT"],
        default_project=os.environ.get("ADO_DEFAULT_PROJECT"),
    )

    repo = os.environ.get("ADO_REPO", "ai-scenarios")
    ado_project = os.environ.get("ADO_DEFAULT_PROJECT", "ai-scenarios")

    terraform_drafter_name = register_terraform_drafter_agent(project)
    reviewer_name = register_reviewer_agent(project)
    publisher_name = register_publisher_agent(project, repo, ado_project)
    summary_email_name = register_summary_email_agent(project)

    def create_drafter_agent() -> Agent:
        return build_terraform_drafter_agent(terraform_drafter_name)

    def create_reviewer_agent() -> Agent:
        return build_reviewer_agent(reviewer_name)

    def create_publisher_agent() -> Agent:
        return build_publisher_agent(publisher_name)

    def create_summary_email_agent() -> Agent:
        return build_summary_email_agent(summary_email_name)

    input_router = InputRouterExecutor()
    drafter_executor = DrafterExecutor(create_drafter_agent)
    reviewer_executor = ReviewerExecutor(create_reviewer_agent, create_drafter_agent)
    publisher_executor = PublisherExecutor(
        create_publisher_agent,
        azure_devops_tools,
        repo,
        ado_project,
    )
    summary_executor = SummaryExecutor(create_summary_email_agent)

    return (
        WorkflowBuilder(start_executor=input_router)
        .add_edge(input_router, drafter_executor)
        .add_edge(drafter_executor, reviewer_executor)
        .add_edge(reviewer_executor, publisher_executor)
        .add_edge(publisher_executor, summary_executor)
        .build()
    )


def create_app() -> AgentFunctionApp:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    workflow = create_workflow()

    function_app = AgentFunctionApp(workflow=workflow, enable_health_check=True)

    credential = AzureCliCredential()
    project = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=credential,
    )
    orchestrator_name = register_orchestrator_agent(project)
    orchestrator_agent = build_orchestrator_agent(orchestrator_name)

    sessions: dict[str, AgentSession] = {}

    @function_app.route(route="chat", methods=["POST"])
    async def chat(req: func.HttpRequest) -> func.HttpResponse:
        try:
            payload = req.get_json()
        except ValueError:
            return func.HttpResponse(
                json.dumps({"error": "Request body must be JSON."}),
                status_code=400,
                mimetype="application/json",
            )

        message = (payload or {}).get("message")
        if not message:
            return func.HttpResponse(
                json.dumps({"error": "Missing 'message' field."}),
                status_code=400,
                mimetype="application/json",
            )

        thread_id = (payload or {}).get("thread_id")
        session = sessions.get(thread_id) if thread_id else None
        if session is None:
            session = orchestrator_agent.create_session(session_id=thread_id)
            sessions[session.session_id] = session

        response = await orchestrator_agent.run(message, session=session)
        reply = extract_response_text(response)

        return func.HttpResponse(
            json.dumps({"thread_id": session.session_id, "reply": reply}),
            status_code=200,
            mimetype="application/json",
        )

    return function_app


app = create_app()
