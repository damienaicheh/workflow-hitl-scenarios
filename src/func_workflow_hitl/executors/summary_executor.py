from collections.abc import Callable

from agent_framework import Agent, Executor, WorkflowContext, handler
from models.publisher_result import PublisherResult
from models.summary_result import SummaryResult
from typing_extensions import Never
from utils.agent_runtime import managed_agent


class SummaryExecutor(Executor):
    """Compose and send a deployment summary email once the PR is created."""

    def __init__(self, agent_factory: Callable[[], Agent]) -> None:
        super().__init__(id="summary_executor")
        self._agent_factory = agent_factory

    @handler
    async def summarize(
        self,
        publisher_result_payload: dict,
        ctx: WorkflowContext[Never, dict[str, object]],
    ) -> None:
        publisher_result = PublisherResult.model_validate(publisher_result_payload)
        recipient_email = ctx.get_state("recipient_email")
        approved_terraform = ctx.get_state("approved_terraform") or ""

        if not recipient_email:
            raise ValueError(
                "Summary step requires recipient_email to be set in the workflow state."
            )

        subject = f"IaC Deployment Ready: PR #{publisher_result.pull_request_id}"
        agent = self._agent_factory()

        async with managed_agent(agent):
            await agent.run(
                "Compose and send the deployment summary email now. "
                f"Recipient email: {recipient_email}\n"
                f"Pull request URL: {publisher_result.pull_request_url}\n"
                f"Branch: {publisher_result.branch_name}\n"
                f"Pull request id: {publisher_result.pull_request_id}\n\n"
                f"Approved Terraform bundle (JSON list of filename/content):\n"
                f"{approved_terraform}"
            )

        summary = SummaryResult(
            publisher_result=publisher_result,
            email_sent_to=recipient_email,
            email_subject=subject,
        )
        await ctx.yield_output(summary.model_dump(mode="json"))
