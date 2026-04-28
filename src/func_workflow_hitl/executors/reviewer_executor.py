from agent_framework import (
    Agent,
    Executor,
    WorkflowContext,
    handler,
    response_handler,
)
from models.publisher_result import PublisherResult
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
        publisher_agent: Agent,
    ) -> None:
        super().__init__(id="reviewer_executor")
        self._reviewer_agent = reviewer_agent
        self._drafter_agent = drafter_agent
        self._publisher_agent = publisher_agent

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
        publisher_result_payload: dict[str, object],
    ) -> ReviewerApprovalRequest:
        prompt = """
                Review the Terraform configuration. 
                Approve it if it is ready, or reject it with feedback.
            """
        return ReviewerApprovalRequest(
            terraform_json=terraform_json,
            summary=summary,
            prompt=prompt,
            publisher_result_payload=publisher_result_payload,
        )

    @handler
    async def review(
        self,
        draft_output: str,
        ctx: WorkflowContext[dict],
    ) -> None:
        async with managed_agent(self._reviewer_agent):
            reviewer_response = await self._reviewer_agent.run(
                f"""
                        Review and update these Terraform files for correctness and readiness.\n
                        Call the available Terraform tools when needed. Return concise human \n
                        Fix the bundle as JSON if necessary.\n\n
                        f"Terraform files:\n{draft_output}
                    """,
                options={"response_format": TerraformBundle},
            )
            try:
                reviewed_bundle = TerraformBundle.model_validate(
                    reviewer_response.value
                )
            except ValidationError as exc:
                raise ValueError(
                    "Reviewer agent did not return a valid Terraform bundle."
                ) from exc

            reviewed_terraform = reviewed_bundle.to_json_list()
            summary = extract_response_text(reviewer_response)

            async with managed_agent(self._publisher_agent):
                response = await self._publisher_agent.run(
                    f"""
                        The Terraform bundle below is already validated and immutable.
                        Do not modify it. Do not ask for confirmation.

                        The available Azure DevOps tools are enough to complete this publication.
                        Decide yourself which tools to call to create the source branch, push the
                        approved Terraform bundle, and create the pull request.
                        For this multi-file Terraform bundle, prefer create_branch, push_terraform_branch,
                        create_pull_request, then optionally get_pull_request to confirm the created PR.
                        Prefer omitting repository and project arguments so the tools use their configured defaults.
                        If you provide them, they must match the configured Azure DevOps project and repository.
                        Return only the final publication result.
                        The final result must contain the actual branch_name, pull_request_id,
                        and pull_request_url returned by successful tool calls.
                        
                        Here is the approved Terraform bundle that has passed review:
                        {reviewed_terraform}
                    """,
                    options={"response_format": PublisherResult},
                )
                try:
                    published_result = PublisherResult.model_validate(response.value)
                except ValidationError as exc:
                    raise ValueError(
                        "Publisher agent did not return a valid publication result."
                    ) from exc

                ctx.set_state("approved_terraform", reviewed_terraform)

                await ctx.request_info(
                    self._build_review_request(
                        reviewed_terraform,
                        summary,
                        published_result.model_dump(mode="json"),
                    ),
                    ReviewerApprovalResponse,
                )

    @response_handler
    async def handle_review(
        self,
        original_request: ReviewerApprovalRequest,
        response: ReviewerApprovalResponse,
        ctx: WorkflowContext[dict],
    ) -> None:
        if response.approved:
            await ctx.send_message(original_request.publisher_result_payload)
            return

        feedback = response.feedback or "Please improve the Terraform configuration."
        async with managed_agent(self._drafter_agent):
            revised = await self._redraft(
                original_request.terraform_json,
                feedback,
            )

        await self.review(revised, ctx)
