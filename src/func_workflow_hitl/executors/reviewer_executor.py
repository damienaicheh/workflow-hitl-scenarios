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
        reviewer_agent: Agent,
        drafter_agent: Agent,
    ) -> None:
        super().__init__(id="reviewer_executor")
        self._reviewer_agent = reviewer_agent
        self._drafter_agent = drafter_agent

    async def _validate_and_summarize(self, terraform_json: str) -> str:
        async with managed_agent(self._reviewer_agent):
            response = await self._reviewer_agent.run(
                f"""
                    Review these Terraform files for correctness and readiness.\n
                    Call the available Terraform tools when needed. Return concise human \n
                    review notes only; do not rewrite the bundle as JSON.\n\n
                    f"Terraform files:\n{terraform_json}
                """
            )
            validation_notes = extract_response_text(response)

            response = await self._reviewer_agent.run(
                f"Summarize this Terraform configuration for human review:\n{terraform_json}"
            )
            summary = extract_response_text(response)

            return f"Validation notes:\n{validation_notes}\n\nSummary:\n{summary}"

    async def _redraft(
        self,
        terraform_json: str,
        feedback: str,
    ) -> str:
        response = await self._drafter_agent.run(
            f"""
                Incorporate ALL of the following feedback and regenerate the 
                Terraform files as a Terraform bundle with a top-level 'files' 
                array. Each file entry must contain only 'filename' and 'content'. 
                Do not include prose or markdown.\n\n
                Current Terraform:\n{terraform_json}\n\n
                Feedback:\n{feedback}
            """,
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
        prompt = """
                Review the Terraform configuration. 
                Approve it if it is ready, or reject it with feedback.
            """
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
        summary = await self._validate_and_summarize(draft_output)
        await ctx.request_info(
            self._build_review_request(
                draft_output,
                summary,
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

        feedback = response.feedback or "Please improve the Terraform configuration."
        async with managed_agent(self._drafter_agent):
            revised = await self._redraft(
                original_request.terraform_json,
                feedback,
            )

        await self.review(revised, ctx)
