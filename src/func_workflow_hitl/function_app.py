import json
import logging
import os
from pathlib import Path

import azure.functions as func
from agent_framework import AgentSession, Workflow, WorkflowBuilder
from agent_framework_azurefunctions import AgentFunctionApp
from agents.orchestrator import create_orchestrator_agent
from agents.publisher import create_publisher_agent
from agents.reviewer import create_reviewer_agent
from agents.summary_email import create_summary_email_agent
from agents.terraform_drafter import create_terraform_drafter_agent
from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from executors.drafter_executor import DrafterExecutor
from executors.finalizer_executor import PublisherExecutor
from executors.input_router_executor import InputRouterExecutor
from executors.reviewer_executor import ReviewerExecutor
from executors.summary_executor import SummaryExecutor
from utils.response_format import extract_response_text

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


def create_workflow() -> Workflow:
    credential = AzureCliCredential()

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
    reviewer_executor = ReviewerExecutor(
        reviewer_agent,
        drafter_agent,
    )
    publisher_executor = PublisherExecutor(
        publisher_agent,
    )
    summary_executor = SummaryExecutor(summary_agent)

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
    orchestrator_agent = create_orchestrator_agent(project)

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
