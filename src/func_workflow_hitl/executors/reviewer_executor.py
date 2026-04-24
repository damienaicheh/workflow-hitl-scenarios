from collections.abc import Callable

from agent_framework import (
    Agent,
    Executor,
    WorkflowContext,
    handler,
    response_handler,
)
from models.reviewer_approval_request import ReviewerApprovalRequest
from models.reviewer_approval_response import ReviewerApprovalResponse
from models.terraform_bundle import TerraformBundle
from pydantic import ValidationError
from utils.agent_runtime import managed_agent
from utils.response_format import extract_response_text


class ReviewerExecutor(Executor):
    def __init__(
        self,
        reviewer_agent_factory: Callable[[], Agent],
        drafter_agent_factory: Callable[[], Agent],
    ) -> None:
        super().__init__(id="reviewer_executor")
        self._reviewer_agent_factory = reviewer_agent_factory
        self._drafter_agent_factory = drafter_agent_factory

    @staticmethod
    def _combine_review_summary(validation_notes: str, summary: str) -> str:
        return f"Validation notes:\n{validation_notes}\n\nSummary:\n{summary}"

    async def _validate(self, reviewer_agent: Agent, terraform_json: str) -> str:
        response = await reviewer_agent.run(
            "Review these Terraform files for correctness and readiness. "
            "Call the available Terraform tools when needed. Return concise human "
            "review notes only; do not rewrite the bundle as JSON.\n\n"
            f"Terraform files:\n{terraform_json}"
        )
        return extract_response_text(response)

    async def _summarize(self, reviewer_agent: Agent, terraform_json: str) -> str:
        response = await reviewer_agent.run(
            f"Summarize this Terraform configuration for human review:\n{terraform_json}"
        )
        return extract_response_text(response)

    async def _redraft(
        self,
        drafter_agent: Agent,
        terraform_json: str,
        feedback: str,
    ) -> str:
        response = await drafter_agent.run(
            "Incorporate ALL of the following feedback and regenerate the "
            "Terraform files as a Terraform bundle with a top-level 'files' "
            "array. Each file entry must contain only 'filename' and 'content'. "
            "Do not include prose or markdown.\n\n"
            f"Current Terraform:\n{terraform_json}\n\n"
            f"Feedback:\n{feedback}",
            options={"response_format": TerraformBundle},
        )
        try:
            bundle = TerraformBundle.model_validate(response.value)
        except ValidationError as exc:
            raise ValueError(
                "Drafter agent did not return a valid Terraform bundle during redraft."
            ) from exc

        return bundle.to_json_list()

    def _build_review_request(
        self,
        terraform_json: str,
        summary: str,
        feedback: str | None = None,
    ) -> ReviewerApprovalRequest:
        prompt = (
            "Review the Terraform configuration. "
            "Approve it if it is ready, or reject it with feedback."
        )
        return ReviewerApprovalRequest(
            terraform_json=terraform_json,
            summary=summary,
            prompt=prompt,
        )

    @handler
    async def review(
        self,
        draft_output: str,
        ctx: WorkflowContext[str],
    ) -> None:
        reviewer_agent = self._reviewer_agent_factory()
        async with managed_agent(reviewer_agent):
            validation_notes = await self._validate(reviewer_agent, draft_output)
            summary = await self._summarize(reviewer_agent, draft_output)
        await ctx.request_info(
            self._build_review_request(
                draft_output,
                self._combine_review_summary(validation_notes, summary),
            ),
            ReviewerApprovalResponse,
        )

    @response_handler
    async def handle_review(
        self,
        original_request: ReviewerApprovalRequest,
        response: ReviewerApprovalResponse,
        ctx: WorkflowContext[str],
    ) -> None:
        if response.approved:
            await ctx.send_message(original_request.terraform_json)
            return

        drafter_agent = self._drafter_agent_factory()
        reviewer_agent = self._reviewer_agent_factory()
        feedback = response.feedback or "Please improve the Terraform configuration."
        async with managed_agent(drafter_agent):
            revised = await self._redraft(
                drafter_agent,
                original_request.terraform_json,
                feedback,
            )

        async with managed_agent(reviewer_agent):
            validation_notes = await self._validate(reviewer_agent, revised)
            summary = await self._summarize(reviewer_agent, revised)
        await ctx.request_info(
            self._build_review_request(
                revised,
                self._combine_review_summary(validation_notes, summary),
                feedback,
            ),
            ReviewerApprovalResponse,
        )
