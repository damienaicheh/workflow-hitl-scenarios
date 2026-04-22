import logging
import os
from pathlib import Path

from agent_framework import (
    Agent,
    Workflow,
    WorkflowBuilder,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework_azurefunctions import AgentFunctionApp
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from executors.drafter_executor import DrafterExecutor
from executors.editor_executor import EditorExecutor
from executors.finalizer_executor import FinalizerExecutor
from executors.input_router_executor import InputRouterExecutor

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


def create_workflow() -> Workflow:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_DEFAULT_MODEL"],
        credential=AzureCliCredential(),
    )

    # Create agents for a sequential document review workflow
    drafter = Agent(
        client=client,
        name="drafter",
        instructions=(
            "You are a document drafter. When given a topic, create a brief draft (2-3 sentences)."
        ),
    )

    editor = Agent(
        client=client,
        name="editor",
        instructions=(
            "You are an editor. Review the draft and make improvements. "
            "Incorporate any human feedback that was provided."
        ),
    )

    finalizer = Agent(
        client=client,
        name="finalizer",
        instructions=(
            "You are a finalizer. Take the edited content and create a polished final version. "
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
