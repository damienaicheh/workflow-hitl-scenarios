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
        agent_factory: Callable[[], Agent],
        azure_devops_tools: AzureDevOpsTools,
        repository: str,
        project: str,
    ) -> None:
        super().__init__(id="publisher_executor")
        self._agent_factory = agent_factory
        self._azure_devops_tools = azure_devops_tools
        self._repository = repository
        self._project = project

    @handler
    async def publish(
        self,
        approved_terraform: str,
        ctx: WorkflowContext[dict],
    ) -> None:
        agent = self._agent_factory()

        async with managed_agent(agent):
            response = await agent.run(
                "The Terraform bundle below is already approved and immutable. "
                "Do not modify it. Do not ask for confirmation. "
                "Return a publication plan with exactly these fields: branch_name, "
                "pull_request_title, and pull_request_description. "
                "Do not claim that a branch or pull request already exists.\n\n"
                f"Approved Terraform bundle:\n{approved_terraform}",
                options={"response_format": PublisherProposal},
            )

        try:
            proposal = PublisherProposal.model_validate(response.value)
        except ValidationError as exc:
            raise ValueError(
                "Publisher agent did not return a valid publication plan."
            ) from exc

        created_branch = await self._azure_devops_tools.create_branch(
            repository=self._repository,
            branch_name=proposal.branch_name,
            project=self._project,
        )
        await self._azure_devops_tools.push_terraform_branch(
            repository=self._repository,
            branch_name=str(created_branch["branch_name"]),
            terraform_files_json=approved_terraform,
            commit_message=proposal.pull_request_title,
            project=self._project,
        )
        pull_request = await self._azure_devops_tools.create_pull_request(
            repository=self._repository,
            branch_name=str(created_branch["branch_name"]),
            title=proposal.pull_request_title,
            description=proposal.pull_request_description,
            project=self._project,
        )

        published_result = PublisherResult(
            branch_name=str(created_branch["branch_name"]),
            pull_request_id=int(pull_request["pull_request_id"]),
            pull_request_url=str(pull_request["pull_request_url"]),
        )

        await self._azure_devops_tools.get_pull_request(
            repository=self._repository,
            pull_request_id=published_result.pull_request_id,
            project=self._project,
        )

        ctx.set_state("approved_terraform", approved_terraform)
        await ctx.send_message(published_result.model_dump(mode="json"))
