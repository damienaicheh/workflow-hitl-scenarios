from agent_framework import (
    Agent,
    Executor,
    WorkflowContext,
    handler,
    response_handler,
)
from models.reviewer_approval_request import ReviewerApprovalRequest
from models.reviewer_approval_response import ReviewerApprovalResponse
from utils.response_format import extract_response_text


class ReviewerExecutor(Executor):
    """Validate Terraform output from the drafter and present for human review.

    Uses a validator agent (with terraform tools) and a reviewer agent
    (for human-readable summaries). Implements the HITL approval loop:
    on rejection, the drafter output is revised incorporating feedback.
    """

    def __init__(self, validator_agent: Agent, reviewer_agent: Agent, drafter_agent: Agent) -> None:
        super().__init__(id="reviewer_executor")
        self._validator = validator_agent
        self._reviewer = reviewer_agent
        self._drafter = drafter_agent

    async def _validate(self, terraform_json: str) -> str:
        response = await self._validator.run(
            f"Validate and format these Terraform files:\n{terraform_json}"
        )
        return extract_response_text(response)

    async def _summarize(self, terraform_json: str) -> str:
        response = await self._reviewer.run(
            f"Summarize this Terraform configuration for human review:\n{terraform_json}"
        )
        return extract_response_text(response)

    async def _redraft(self, terraform_json: str, feedback: str) -> str:
        response = await self._drafter.run(
            "Incorporate ALL of the following feedback and regenerate the "
            "Terraform files as a JSON list.\n\n"
            f"Current Terraform:\n{terraform_json}\n\n"
            f"Feedback:\n{feedback}"
        )
        return extract_response_text(response)

    def _build_review_request(
        self,
        terraform_json: str,
        summary: str,
        feedback: str | None = None,
    ) -> ReviewerApprovalRequest:
        prompt = (
            "Review the Terraform configuration below. "
            "Approve it if it is ready, or reject it with feedback.\n\n"
            f"Summary:\n{summary}"
        )
        if feedback:
            prompt = f"{prompt}\n\nPrevious feedback applied:\n{feedback}"

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
        validated = await self._validate(draft_output)
        summary = await self._summarize(validated)
        await ctx.request_info(
            self._build_review_request(validated, summary),
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

        feedback = response.feedback or "Please improve the Terraform configuration."
        revised = await self._redraft(original_request.terraform_json, feedback)
        validated = await self._validate(revised)
        summary = await self._summarize(validated)
        await ctx.request_info(
            self._build_review_request(validated, summary, feedback),
            ReviewerApprovalResponse,
        )
