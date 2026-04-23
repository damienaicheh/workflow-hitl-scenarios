from agent_framework import (
    Agent,
    Executor,
    WorkflowContext,
    handler,
)
from typing_extensions import Never
from utils.response_format import extract_response_text


class PublisherExecutor(Executor):
    """Push approved Terraform to Azure DevOps and create a Pull Request."""

    def __init__(self, agent: Agent) -> None:
        super().__init__(id="publisher_executor")
        self._agent = agent

    @handler
    async def publish(
        self,
        approved_terraform: str,
        ctx: WorkflowContext[Never, str],
    ) -> None:
        response = await self._agent.run(
            "Push the following approved Terraform files to the repository "
            "using push_terraform_branch, then create a Pull Request using "
            "create_pull_request. Output the PR URL.\n\n"
            f"Terraform files:\n{approved_terraform}"
        )
        await ctx.yield_output(extract_response_text(response))
