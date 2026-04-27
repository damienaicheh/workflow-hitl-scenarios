import os
from collections.abc import Callable

from agent_framework import Agent, Executor, WorkflowContext, handler
from models.publisher_result import PublisherResult
from pydantic import BaseModel, ValidationError
from tools.azure_devops_tools import AzureDevOpsTools
from utils.agent_runtime import managed_agent


class PublisherProposal(BaseModel):
    branch_name: str
    pull_request_title: str
    pull_request_description: str


class PublisherExecutor(Executor):
    """Create a branch, push approved Terraform, and open a Pull Request."""

    def __init__(
        self,
        publisher_agent: Agent,
    ) -> None:
        super().__init__(id="publisher_executor")
        self._publisher_agent = publisher_agent

    @handler
    async def publish(
        self,
        approved_terraform: str,
        ctx: WorkflowContext[dict],
    ) -> None:
        ado_project = os.environ["ADO_DEFAULT_PROJECT"]

        azure_devops_tools = AzureDevOpsTools(
            organization=os.environ["ADO_ORG"],
            auth_token=os.environ["ADO_PAT"],
            default_project=ado_project,
        )

        repository = os.environ["ADO_REPO"]

        async with managed_agent(self._publisher_agent):
            response = await self._publisher_agent.run(
                f"""
                    The Terraform bundle below is already approved and immutable.
                    Do not modify it. Do not ask for confirmation.
                    Return a publication plan with exactly these fields: branch_name,
                    pull_request_title, and pull_request_description.
                    Do not claim that a branch or pull request already exists.\n\n
                    Approved Terraform bundle:\n{approved_terraform}
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
            repository=repository,
            branch_name=proposal.branch_name,
            project=ado_project,
        )
        await azure_devops_tools.push_terraform_branch(
            repository=repository,
            branch_name=str(created_branch["branch_name"]),
            terraform_files_json=approved_terraform,
            commit_message=proposal.pull_request_title,
            project=ado_project,
        )
        pull_request = await azure_devops_tools.create_pull_request(
            repository=repository,
            branch_name=str(created_branch["branch_name"]),
            title=proposal.pull_request_title,
            description=proposal.pull_request_description,
            project=ado_project,
        )

        published_result = PublisherResult(
            branch_name=str(created_branch["branch_name"]),
            pull_request_id=int(pull_request["pull_request_id"]),
            pull_request_url=str(pull_request["pull_request_url"]),
        )

        await azure_devops_tools.get_pull_request(
            repository=repository,
            pull_request_id=published_result.pull_request_id,
            project=ado_project,
        )

        ctx.set_state("approved_terraform", approved_terraform)
        await ctx.send_message(published_result.model_dump(mode="json"))
