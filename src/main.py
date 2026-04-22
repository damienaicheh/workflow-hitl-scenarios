# Multi-agent workflow that generates Terraform code, validates it,
# and loops for human review before pushing to Azure DevOps.
#
# Architecture:
#   Phase 1 (iterative review loop):
#     drafter → validator → reviewer [HITL PAUSE]
#          ↑                           │
#          └── feedback ←──────────────┘
#
#   Phase 2 (deployment — runs once after approval):
#     publisher → notifier → deployer → reporter
#
# Prerequisites:
# - FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_DEFAULT_MODEL set in .env
# - ADO_ORG, ADO_PAT set for Azure DevOps operations
# - Authentication via az login

import asyncio
import base64
import os
from collections.abc import AsyncIterable
from typing import cast

from agent_framework import (
    Agent,
    AgentExecutorResponse,
    MCPStdioTool,
    Message,
    WorkflowEvent,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import AgentRequestInfoResponse, SequentialBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from tools.azure_devops_tools import AzureDevOpsTools
from tools.pipeline_tools import PipelineTools
from tools.teams_tools import TeamsTools
from tools.terraform_tools import TerraformTools

load_dotenv()

MAX_REVIEW_ITERATIONS = 5


# ── Environment helpers

def get_first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def require_env(*names: str) -> str:
    value = get_first_env(*names)
    if value:
        return value
    joined_names = ", ".join(names)
    raise ValueError(
        f"Missing required environment variable. Set one of: {joined_names}"
    )


def resolve_ado_org() -> str:
    return require_env("ADO_ORG").removeprefix("https://dev.azure.com/").strip("/")


def resolve_pat_credential() -> str:
    raw_pat = get_first_env("ADO_PAT")
    if not raw_pat:
        raise ValueError("PAT auth requires ADO_PAT.")
    pat_identity = "ado@example.invalid"
    return base64.b64encode(f"{pat_identity}:{raw_pat}".encode("utf-8")).decode("utf-8")


def resolve_ado_domains() -> list[str]:
    raw_domains = get_first_env("ADO_DOMAINS")
    if not raw_domains:
        return []
    return [domain.strip() for domain in raw_domains.split(",") if domain.strip()]


def build_ado_mcp_tool() -> MCPStdioTool:
    tool_args = [
        "-y",
        "@azure-devops/mcp",
        resolve_ado_org(),
        "--authentication",
        "pat",
    ]
    for domain in resolve_ado_domains():
        tool_args.extend(["-d", domain])

    return MCPStdioTool(
        name="azure_devops",
        command="npx",
        args=tool_args,
        env={"PERSONAL_ACCESS_TOKEN": resolve_pat_credential()},
        load_prompts=False,
        approval_mode="never_require",
        description="Azure DevOps tools exposed through the local Azure DevOps MCP server.",
    )


# ── Phase 1: Review stream handler ──────────────────────────────────

async def process_review_stream(
    stream: AsyncIterable[WorkflowEvent],
) -> tuple[bool, str | None, str | None]:
    """Process the review workflow stream.

    Returns:
        (approved, human_feedback_or_none, last_agent_output)
    """
    requests: dict[str, AgentExecutorResponse] = {}
    last_output: str | None = None

    async for event in stream:
        if event.type == "request_info" and isinstance(
            event.data, AgentExecutorResponse
        ):
            requests[event.request_id] = event.data

        elif event.type == "output":
            outputs = cast(list[Message], event.data)
            for message in outputs:
                if message.text:
                    last_output = message.text

    if not requests:
        return True, None, last_output

    for request_id, request in requests.items():
        agent_text = request.agent_response.text or ""

        print("\n" + "-" * 60)
        print("REVIEW: Terraform plan ready for your approval")
        print("-" * 60)
        print(agent_text[:2000])
        print("-" * 60)

        if request.full_conversation:
            print("Conversation context:")
            recent = (
                request.full_conversation[-3:]
                if len(request.full_conversation) > 3
                else request.full_conversation
            )
            for msg in recent:
                name = msg.author_name or msg.role
                text = (msg.text or "")[:300]
                print(f"  [{name}]: {text}")
            print("-" * 60)

        user_input = input(  # noqa: ASYNC250
            "\nType 'approve' to proceed to deployment, or describe changes needed:\n> "
        )

        if user_input.strip().lower() in ("approve", "skip", "ok", "yes", "lgtm"):
            return True, None, agent_text
        else:
            return False, user_input.strip(), agent_text

    return True, None, last_output


# ── Phase 2: Deploy stream handler ──────────────────────────────────

async def process_deploy_stream(
    stream: AsyncIterable[WorkflowEvent],
) -> dict[str, AgentRequestInfoResponse] | None:
    """Process the deployment workflow stream."""
    requests: dict[str, AgentExecutorResponse] = {}
    async for event in stream:
        if event.type == "request_info" and isinstance(
            event.data, AgentExecutorResponse
        ):
            requests[event.request_id] = event.data

        elif event.type == "output":
            print("\n" + "=" * 60)
            print("DEPLOYMENT COMPLETE")
            print("=" * 60)
            outputs = cast(list[Message], event.data)
            for message in outputs:
                if message.text:
                    print(f"[{message.author_name or message.role}]: {message.text}")

    responses: dict[str, AgentRequestInfoResponse] = {}
    if requests:
        for request_id, request in requests.items():
            print("\n" + "-" * 40)
            print(f"Agent '{request.executor_id}' requests input:")
            print(request.agent_response.text[:500])
            print("-" * 40)

            user_input = input("Your decision (or 'approve'): ")  # noqa: ASYNC250
            if user_input.strip().lower() in ("approve", "skip", "ok", "yes"):
                responses[request_id] = AgentRequestInfoResponse.approve()
            else:
                responses[request_id] = AgentRequestInfoResponse.from_strings(
                    [user_input]
                )

    return responses if responses else None


# ── Main ─────────────────────────────────────────────────────────────

async def main() -> None:
    credential = AzureCliCredential()
    default_project = get_first_env("ADO_DEFAULT_PROJECT")

    # Foundry clients
    default_client = FoundryChatClient(
        project_endpoint=require_env("FOUNDRY_PROJECT_ENDPOINT"),
        model=require_env("FOUNDRY_DEFAULT_MODEL"),
        credential=credential,
    )
    orchestrator_model = get_first_env("FOUNDRY_ORCHESTRATOR_MODEL")
    orchestrator_client = (
        FoundryChatClient(
            project_endpoint=require_env("FOUNDRY_PROJECT_ENDPOINT"),
            model=orchestrator_model,
            credential=credential,
        )
        if orchestrator_model
        else default_client
    )

    # Tool instances
    ado_tools = AzureDevOpsTools(
        organization=resolve_ado_org(),
        auth_token=resolve_pat_credential(),
        default_project=default_project,
    )
    terraform_tools = TerraformTools()
    pipeline_tools = PipelineTools(
        organization=resolve_ado_org(),
        auth_token=resolve_pat_credential(),
        default_project=default_project,
    )

    teams_webhook = get_first_env("TEAMS_WEBHOOK_URL")
    teams_tools = TeamsTools(webhook_url=teams_webhook) if teams_webhook else None

    # ── Phase 1 agents: draft → validate → review (iterative) ────

    drafter = Agent(
        client=orchestrator_client,
        name="drafter",
        instructions=(
            "You are a Terraform expert. Given a user request for Azure infrastructure, "
            "generate the necessary .tf files. Output them as a JSON list: "
            '[{"filename": "main.tf", "content": "..."}, ...]. '
            "Follow Azure best practices and use azurerm provider. "
            "If previous feedback is provided, incorporate it into the new version."
        ),
    )

    validator = Agent(
        client=default_client,
        name="validator",
        instructions=(
            "You are an IaC validator. Take the Terraform files produced by the drafter "
            "and run validate_terraform and format_terraform on them. "
            "If validation fails, describe the errors clearly. "
            "If it passes, output the formatted files as the same JSON list."
        ),
        tools=[
            terraform_tools.validate_terraform,
            terraform_tools.format_terraform,
        ],
    )

    reviewer = Agent(
        client=default_client,
        name="reviewer",
        instructions=(
            "You are a Terraform reviewer. Present the validated Terraform configuration "
            "in a clear, human-readable summary:\n"
            "1. List each resource that will be created (type, name, key settings)\n"
            "2. Highlight the Azure region, SKU/tier, and any cost-relevant choices\n"
            "3. Flag any potential issues or recommendations\n"
            "End with: 'Please approve or provide feedback for changes.'"
        ),
    )

    # ── Phase 2 agents: publish → notify → deploy → report ───────

    ado_repo = "ai-scenarios"  # repo name in the ADO project

    publisher = Agent(
        client=default_client,
        name="publisher",
        instructions=(
            "You are a Git operations specialist. Take the validated Terraform files "
            f"and push them to the repository '{ado_repo}' in Azure DevOps "
            "using push_terraform_branch. Use the repository name exactly as given. "
            "Then create a Pull Request using create_pull_request. "
            "Output the PR URL."
        ),
        tools=[
            build_ado_mcp_tool(),
            ado_tools.push_terraform_branch,
            ado_tools.create_pull_request,
        ],
    )

    notifier_tools = []
    notifier_instructions = [
        "You are a notification agent. Summarize the deployment plan "
        "and the PR that was created.",
    ]
    if teams_tools:
        notifier_tools.append(teams_tools.send_teams_approval_card)
        notifier_instructions.append(
            "Send an Adaptive Card to Teams with the deployment summary and PR link."
        )
    notifier_instructions.append(
        "Output a clear summary of what was published."
    )

    notifier = Agent(
        client=default_client,
        name="notifier",
        instructions=" ".join(notifier_instructions),
        tools=notifier_tools,
    )

    deployer = Agent(
        client=default_client,
        name="deployer",
        instructions=(
            "You are a deployment monitor. After human approval, "
            "check the pipeline status using get_pipeline_runs. "
            "Report whether the deployment succeeded or failed."
        ),
        tools=[
            pipeline_tools.get_pipeline_runs,
            pipeline_tools.get_pipeline_run_status,
        ],
    )

    reporter_tools = []
    reporter_instructions = [
        "You are a final reporter. Summarize the entire deployment workflow: "
        "what was generated, validated, reviewed, pushed, and deployed.",
    ]
    if teams_tools:
        reporter_tools.append(teams_tools.send_teams_status_card)
        reporter_instructions.append(
            "Send a final status card to Teams."
        )

    reporter = Agent(
        client=default_client,
        name="reporter",
        instructions=" ".join(reporter_instructions),
        tools=reporter_tools,
    )

    # ── Run ───────────────────────────────────────────────────────

    print("=" * 60)
    print("POC 6 – IaC Deployment Assistant (HITL)")
    print("=" * 60)
    user_request = input("Describe the Azure infrastructure you need:\n> ")

    # ── Phase 1: Iterative review loop ────────────────────────────
    # drafter → validator → reviewer [HITL PAUSE]
    # Loops until the human approves or max iterations reached.

    feedback_history: list[str] = []
    approved_terraform: str | None = None

    for iteration in range(1, MAX_REVIEW_ITERATIONS + 1):
        print(f"\n{'='*60}")
        print(f"REVIEW ITERATION {iteration}/{MAX_REVIEW_ITERATIONS}")
        print("=" * 60)

        # Build the prompt: original request + accumulated feedback
        if feedback_history:
            feedback_block = "\n".join(
                f"  {i}. {fb}" for i, fb in enumerate(feedback_history, 1)
            )
            prompt = (
                f"{user_request}\n\n"
                f"IMPORTANT — The reviewer requested these changes:\n"
                f"{feedback_block}\n\n"
                f"Regenerate the Terraform files incorporating ALL the feedback above."
            )
        else:
            prompt = user_request

        # Fresh review workflow each iteration (clean state)
        review_workflow = (
            SequentialBuilder(participants=[drafter, validator, reviewer])
            .with_request_info(agents=["reviewer"])
            .build()
        )

        stream = review_workflow.run(prompt, stream=True)
        approved, feedback, terraform_output = await process_review_stream(stream)

        if approved:
            approved_terraform = terraform_output
            print("\n✓ Terraform approved!")
            break
        else:
            feedback_history.append(feedback)
            print(f"\n✗ Feedback recorded: '{feedback}'")
            print("  Re-drafting with feedback...")

    if not approved_terraform:
        print(f"\n✗ Not approved after {MAX_REVIEW_ITERATIONS} iterations. Exiting.")
        return

    # ── Phase 2: Deployment ───────────────────────────────────────
    # publisher → notifier → deployer → reporter (linear, runs once)

    print(f"\n{'='*60}")
    print("PHASE 2: DEPLOYMENT")
    print("=" * 60)

    deploy_workflow = (
        SequentialBuilder(
            participants=[publisher, notifier, deployer, reporter]
        )
        .build()
    )

    deploy_prompt = (
        f"The following Terraform has been reviewed and approved by the human.\n\n"
        f"Original request: {user_request}\n\n"
        f"Approved Terraform summary:\n{approved_terraform}"
    )

    stream = deploy_workflow.run(deploy_prompt, stream=True)
    pending = await process_deploy_stream(stream)
    while pending is not None:
        stream = deploy_workflow.run(stream=True, responses=pending)
        pending = await process_deploy_stream(stream)


if __name__ == "__main__":
    asyncio.run(main())
