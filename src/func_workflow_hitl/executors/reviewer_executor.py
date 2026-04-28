import os

from agent_framework import (
    Agent,
    Executor,
    WorkflowContext,
    handler,
    response_handler,
)
from models.publisher_proposal import PublisherProposal
from models.publisher_result import PublisherResult
from models.reviewer_approval_request import ReviewerApprovalRequest
from models.reviewer_approval_response import ReviewerApprovalResponse
from models.terraform_bundle import TerraformBundle
from pydantic import ValidationError
from tools.azure_devops_tools import AzureDevOpsTools
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
        self._ado_project = os.environ["ADO_DEFAULT_PROJECT"]
        self._ado_repository = os.environ["ADO_REPO"]

    # async def _validate_and_summarize(self, terraform_json: str) -> str:
    #     async with managed_agent(self._reviewer_agent):

    #         response = await self._reviewer_agent.run(
    #             f"Summarize this Terraform configuration for human review:\n{terraform_json}"
    #         )
    #         summary = extract_response_text(response)

    #         return f"Validation notes:\n{validation_notes}\n\nSummary:\n{summary}"

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

            azure_devops_tools = AzureDevOpsTools(
                organization=os.environ["ADO_ORG"],
                auth_token=os.environ["ADO_PAT"],
                default_project=self._ado_project,
            )

            async with managed_agent(self._publisher_agent):
                response = await self._publisher_agent.run(
                    f"""
                        The Terraform bundle below is already validated and immutable.
                        Do not modify it. Do not ask for confirmation.
                        Return a publication plan with exactly these fields: branch_name,
                        pull_request_title, and pull_request_description.
                        Do not claim that a branch or pull request already exists.\n\n
                        Approved Terraform bundle:\n{reviewed_terraform}
                    """,
                    options={"response_format": PublisherProposal},
                )
                try:
                    proposal = PublisherProposal.model_validate(response.value)
                except ValidationError as exc:
                    raise ValueError(
                        "Publisher agent did not return a valid publication plan."
                    ) from exc

                created_branch = await azure_devops_tools.create_branch(
                    repository=self._ado_repository,
                    branch_name=proposal.branch_name,
                    project=self._ado_project,
                )
                await azure_devops_tools.push_terraform_branch(
                    repository=self._ado_repository,
                    branch_name=str(created_branch["branch_name"]),
                    terraform_files_json=reviewed_terraform,
                    commit_message=proposal.pull_request_title,
                    project=self._ado_project,
                )
                pull_request = await azure_devops_tools.create_pull_request(
                    repository=self._ado_repository,
                    branch_name=str(created_branch["branch_name"]),
                    title=proposal.pull_request_title,
                    description=proposal.pull_request_description,
                    project=self._ado_project,
                )

                published_result = PublisherResult(
                    branch_name=str(created_branch["branch_name"]),
                    pull_request_id=int(pull_request["pull_request_id"]),
                    pull_request_url=str(pull_request["pull_request_url"]),
                )

                await azure_devops_tools.get_pull_request(
                    repository=self._ado_repository,
                    pull_request_id=published_result.pull_request_id,
                    project=self._ado_project,
                )

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
