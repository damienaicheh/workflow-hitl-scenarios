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
from executors.editor_executor import ReviewerExecutor
from executors.finalizer_executor import PublisherExecutor
from executors.input_router_executor import InputRouterExecutor
from tools.azure_devops_tools import AzureDevOpsTools
from tools.terraform_tools import TerraformTools

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


def create_workflow() -> Workflow:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_DEFAULT_MODEL"],
        credential=AzureCliCredential(),
    )

    terraform_tools = TerraformTools()

    drafter = Agent(
        client=client,
        name="drafter",
        instructions=(
            "You are a Terraform expert. Given a user request for Azure "
            "infrastructure, generate the necessary .tf files. Output them as "
            'a JSON list: [{"filename": "main.tf", "content": "..."}, ...]. '
            "Follow Azure best practices and use azurerm provider. "
            "If previous feedback is provided, incorporate ALL of it."
        ),
    )

    validator = Agent(
        client=client,
        name="validator",
        instructions=(
            "You are an IaC validator. Run validate_terraform and "
            "format_terraform on the Terraform files from the drafter. "
            "If validation fails, describe the errors. "
            "If it passes, output the formatted files as the same JSON list."
        ),
        tools=[
            terraform_tools.validate_terraform,
            terraform_tools.format_terraform,
        ],
    )

    reviewer = Agent(
        client=client,
        name="reviewer",
        instructions=(
            "You are a Terraform reviewer. Present the validated Terraform "
            "configuration in a clear summary:\n"
            "1. List each resource (type, name, key settings)\n"
            "2. Highlight region, SKU/tier, and cost-relevant choices\n"
            "3. Flag potential issues or recommendations\n"
            "End with: 'Please approve or provide feedback for changes.'"
        ),
    )

    pat_b64 = base64.b64encode(
        f"ado@agent:{os.environ['ADO_PAT']}".encode()
    ).decode()
    ado_tools = AzureDevOpsTools(
        organization=os.environ["ADO_ORG"],
        auth_token=pat_b64,
        default_project=os.environ.get("ADO_DEFAULT_PROJECT"),
    )

    repo = os.environ.get("ADO_REPO", "ai-scenarios")
    publisher = Agent(
        client=client,
        name="publisher",
        instructions=(
            "You are a Git operations specialist. Push the validated Terraform "
            f"files to the repository '{repo}' using push_terraform_branch. "
            "Then create a Pull Request using create_pull_request. "
            "Output the PR URL."
        ),
        tools=[
            ado_tools.push_terraform_branch,
            ado_tools.create_pull_request,
        ],
    )

    input_router = InputRouterExecutor()
    drafter_executor = DrafterExecutor(drafter)
    reviewer_executor = ReviewerExecutor(validator, reviewer, drafter)
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
