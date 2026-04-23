import logging
import sys
from pathlib import Path

from agent_framework import (
    Agent,
    Workflow,
    WorkflowBuilder,
)
from agent_framework_azurefunctions import AgentFunctionApp
from executors.drafter_executor import DrafterExecutor
from executors.editor_executor import EditorExecutor
from executors.finalizer_executor import FinalizerExecutor
from executors.input_router_executor import InputRouterExecutor

# Make the parent `src/` importable so we can reuse config.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402


def create_workflow() -> Workflow:
    client = config.default_client()

    # Create agents for a sequential IaC review workflow
    drafter = Agent(
        client=client,
        name="drafter",
        instructions=config.load_prompt("drafter"),
    )

    editor = Agent(
        client=client,
        name="editor",
        instructions=config.load_prompt("reviewer"),
    )

    finalizer = Agent(
        client=client,
        name="finalizer",
        instructions=(
            "You are a finalizer. Take the reviewed Terraform configuration "
            "and produce a polished final version ready for deployment. "
            "Incorporate any additional feedback provided."
        ),
    )

    input_router = InputRouterExecutor()
    drafter_executor = DrafterExecutor(drafter)
    editor_executor = EditorExecutor(editor)
    finalizer_executor = FinalizerExecutor(finalizer)

    workflow = (
        WorkflowBuilder(start_executor=input_router)
        .add_edge(input_router, drafter_executor)
        .add_edge(drafter_executor, editor_executor)
        .add_edge(editor_executor, finalizer_executor)
        .build()
    )

    return workflow


def create_app() -> AgentFunctionApp:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    workflow = create_workflow()
    return AgentFunctionApp(workflow=workflow, enable_health_check=True)


app = create_app()
