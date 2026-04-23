# Copyright (c) Microsoft. All rights reserved.

"""IaC Deployment Assistant — multi-agent HITL workflow.

Architecture
~~~~~~~~~~~~
Phase 1 — iterative review loop::

    drafter → validator → reviewer  [HITL PAUSE]
         ↑                           │
         └── human feedback ←────────┘

Phase 2 — deployment (runs once after approval)::

    publisher → notifier → deployer → reporter

Prerequisites
~~~~~~~~~~~~~
- ``FOUNDRY_PROJECT_ENDPOINT`` and ``FOUNDRY_DEFAULT_MODEL`` in .env
- ``ADO_ORG``, ``ADO_PAT`` for Azure DevOps operations
- ``az login`` for Foundry authentication
"""

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import cast

from agent_framework import Agent, AgentExecutorResponse, Message, WorkflowEvent
from agent_framework.orchestrations import AgentRequestInfoResponse, SequentialBuilder

import config
from tools.azure_devops_tools import AzureDevOpsTools
from tools.pipeline_tools import PipelineTools
from tools.teams_tools import TeamsTools
from tools.terraform_tools import TerraformTools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("iac-assistant")

MAX_REVIEW_ITERATIONS = 5
APPROVE_KEYWORDS = frozenset({"approve", "skip", "ok", "yes", "lgtm"})


# ── Phase 1: Review stream handler ──────────────────────────────────

async def process_review_stream(
    stream: AsyncIterable[WorkflowEvent],
) -> tuple[bool, str | None, str | None]:
    """Consume the review workflow stream, pausing for human input.

    Returns ``(approved, feedback_or_none, last_agent_output)``.
    """
    requests: dict[str, AgentExecutorResponse] = {}
    last_output: str | None = None

    async for event in stream:
        if event.type == "request_info" and isinstance(
            event.data, AgentExecutorResponse
        ):
            requests[event.request_id] = event.data
        elif event.type == "output":
            for msg in cast(list[Message], event.data):
                if msg.text:
                    last_output = msg.text

    if not requests:
        return True, None, last_output

    for _rid, request in requests.items():
        agent_text = request.agent_response.text or ""

        log.info("Review ready — presenting to human")
        print("\n" + "─" * 60)
        print("  REVIEW: Terraform plan ready for your approval")
        print("─" * 60)
        print(agent_text[:2000])
        print("─" * 60)

        user_input = input(  # noqa: ASYNC250
            "\nType 'approve' to deploy, or describe changes:\n> "
        )

        if user_input.strip().lower() in APPROVE_KEYWORDS:
            return True, None, agent_text
        return False, user_input.strip(), agent_text

    return True, None, last_output


# ── Phase 2: Deploy stream handler ──────────────────────────────────

async def process_deploy_stream(
    stream: AsyncIterable[WorkflowEvent],
) -> dict[str, AgentRequestInfoResponse] | None:
    """Consume the deployment workflow stream, collecting any HITL prompts."""
    requests: dict[str, AgentExecutorResponse] = {}

    async for event in stream:
        if event.type == "request_info" and isinstance(
            event.data, AgentExecutorResponse
        ):
            requests[event.request_id] = event.data
        elif event.type == "output":
            log.info("Deployment pipeline finished")
            print("\n" + "═" * 60)
            print("  DEPLOYMENT COMPLETE")
            print("═" * 60)
            for msg in cast(list[Message], event.data):
                if msg.text:
                    print(f"  [{msg.author_name or msg.role}]  {msg.text}")

    if not requests:
        return None

    responses: dict[str, AgentRequestInfoResponse] = {}
    for request_id, request in requests.items():
        print(f"\n  Agent '{request.executor_id}' requests input:")
        print(f"  {request.agent_response.text[:500]}")
        user_input = input("  Your decision (or 'approve'): ")  # noqa: ASYNC250

        if user_input.strip().lower() in APPROVE_KEYWORDS:
            responses[request_id] = AgentRequestInfoResponse.approve()
        else:
            responses[request_id] = AgentRequestInfoResponse.from_strings(
                [user_input]
            )
    return responses


# ── Agent definitions ────────────────────────────────────────────────


def _build_agents(
    llm: object,
    orchestrator_llm: object,
    ado_tools: AzureDevOpsTools,
    terraform_tools: TerraformTools,
    pipeline_tools: PipelineTools,
    teams_tools: TeamsTools | None,
) -> dict[str, Agent]:
    """Construct all agents once, return them keyed by name."""

    repo = config.ado_repo()

    agents: dict[str, Agent] = {}

    # Phase 1 ─────────────────────────────────────────────────────

    agents["drafter"] = Agent(
        client=orchestrator_llm,
        name="drafter",
        instructions=config.load_prompt("drafter"),
    )

    agents["validator"] = Agent(
        client=llm,
        name="validator",
        instructions=config.load_prompt("validator"),
        tools=[
            terraform_tools.validate_terraform,
            terraform_tools.format_terraform,
        ],
    )

    agents["reviewer"] = Agent(
        client=llm,
        name="reviewer",
        instructions=config.load_prompt("reviewer"),
    )

    # Phase 2 ─────────────────────────────────────────────────────

    agents["publisher"] = Agent(
        client=llm,
        name="publisher",
        instructions=config.load_prompt("publisher", repo=repo),
        tools=[
            config.build_mcp_tool(),
            ado_tools.push_terraform_branch,
            ado_tools.create_pull_request,
        ],
    )

    notifier_tools: list = []
    notifier_instructions = config.load_prompt("notifier")
    if teams_tools:
        notifier_tools.append(teams_tools.send_teams_approval_card)

    agents["notifier"] = Agent(
        client=llm,
        name="notifier",
        instructions=notifier_instructions,
        tools=notifier_tools,
    )

    agents["deployer"] = Agent(
        client=llm,
        name="deployer",
        instructions=config.load_prompt("deployer"),
        tools=[
            pipeline_tools.get_pipeline_runs,
            pipeline_tools.get_pipeline_run_status,
        ],
    )

    reporter_tools: list = []
    if teams_tools:
        reporter_tools.append(teams_tools.send_teams_status_card)

    agents["reporter"] = Agent(
        client=llm,
        name="reporter",
        instructions=config.load_prompt("reporter"),
        tools=reporter_tools,
    )

    return agents


# ── Main ─────────────────────────────────────────────────────────────


async def main() -> None:
    credential = config.foundry_credential()
    llm = config.default_client(credential)
    orchestrator_llm = config.orchestrator_client(credential)

    ado_tools = AzureDevOpsTools(
        organization=config.ado_org(),
        auth_token=config.ado_pat_b64(),
        default_project=config.ado_project(),
    )
    terraform_tools = TerraformTools()
    pipeline_tools = PipelineTools(
        organization=config.ado_org(),
        auth_token=config.ado_pat_b64(),
        default_project=config.ado_project(),
    )

    webhook = config.get_env("TEAMS_WEBHOOK_URL")
    teams_tools = TeamsTools(webhook_url=webhook) if webhook else None

    agents = _build_agents(
        llm, orchestrator_llm, ado_tools, terraform_tools, pipeline_tools, teams_tools,
    )

    # ── Prompt ────────────────────────────────────────────────────

    print("═" * 60)
    print("  IaC Deployment Assistant")
    print("═" * 60)
    user_request = input("Describe the Azure infrastructure you need:\n> ")

    # ── Phase 1: iterative review loop ────────────────────────────

    feedback_history: list[str] = []
    approved_terraform: str | None = None

    for iteration in range(1, MAX_REVIEW_ITERATIONS + 1):
        log.info("Review iteration %d/%d", iteration, MAX_REVIEW_ITERATIONS)
        print(f"\n{'─'*60}")
        print(f"  ITERATION {iteration}/{MAX_REVIEW_ITERATIONS}")
        print("─" * 60)

        if feedback_history:
            feedback_block = "\n".join(
                f"  {i}. {fb}" for i, fb in enumerate(feedback_history, 1)
            )
            prompt = (
                f"{user_request}\n\n"
                f"IMPORTANT — incorporate these changes:\n{feedback_block}\n\n"
                f"Regenerate the Terraform files with ALL feedback above."
            )
        else:
            prompt = user_request

        review_wf = (
            SequentialBuilder(
                participants=[agents["drafter"], agents["validator"], agents["reviewer"]],
            )
            .with_request_info(agents=["reviewer"])
            .build()
        )

        stream = review_wf.run(prompt, stream=True)
        approved, feedback, terraform_output = await process_review_stream(stream)

        if approved:
            approved_terraform = terraform_output
            log.info("Terraform approved after %d iteration(s)", iteration)
            print("\n  ✓ Terraform approved!")
            break

        feedback_history.append(feedback)
        log.info("Feedback #%d: %s", iteration, feedback)
        print(f"\n  ✗ Feedback recorded — re-drafting…")

    if not approved_terraform:
        log.warning("Not approved after %d iterations", MAX_REVIEW_ITERATIONS)
        print(f"\n  ✗ Not approved after {MAX_REVIEW_ITERATIONS} iterations. Exiting.")
        return

    # ── Phase 2: deployment ───────────────────────────────────────

    log.info("Starting deployment phase")
    print(f"\n{'═'*60}")
    print("  PHASE 2: DEPLOYMENT")
    print("═" * 60)

    deploy_wf = (
        SequentialBuilder(
            participants=[
                agents["publisher"],
                agents["notifier"],
                agents["deployer"],
                agents["reporter"],
            ],
        )
        .build()
    )

    deploy_prompt = (
        f"The following Terraform has been reviewed and approved.\n\n"
        f"Original request: {user_request}\n\n"
        f"Approved Terraform:\n{approved_terraform}"
    )

    stream = deploy_wf.run(deploy_prompt, stream=True)
    pending = await process_deploy_stream(stream)
    while pending is not None:
        stream = deploy_wf.run(stream=True, responses=pending)
        pending = await process_deploy_stream(stream)


if __name__ == "__main__":
    asyncio.run(main())
