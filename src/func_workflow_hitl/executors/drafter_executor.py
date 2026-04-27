from collections.abc import Callable

from agent_framework import (
    Agent,
    Executor,
    WorkflowContext,
    handler,
)
from models.terraform_bundle import TerraformBundle
from pydantic import ValidationError
from utils.agent_runtime import managed_agent


class DrafterExecutor(Executor):
    """Generate Terraform files from a natural-language infrastructure request."""

    def __init__(self, drafter_agent: Agent) -> None:
        super().__init__(id="drafter_executor")
        self._drafter_agent = drafter_agent

    @handler
    async def draft(
        self,
        prompt: str,
        ctx: WorkflowContext[str],
    ) -> None:
        instruction = f"""
            Generate the Terraform .tf files for the following Azure
            infrastructure request. Return a Terraform bundle with a top-level
            'files' array. Each file entry must contain only 'filename' and
            'content'.
            Follow Azure best practices and use azurerm provider.\n\n
            Request:\n{prompt}
        """

        async with managed_agent(self._drafter_agent):
            response = await self._drafter_agent.run(
                instruction,
                options={"response_format": TerraformBundle},
            )

        try:
            bundle = TerraformBundle.model_validate(response.value)
        except ValidationError as exc:
            raise ValueError(
                "Drafter agent did not return a valid Terraform bundle."
            ) from exc

        await ctx.send_message(bundle.to_json_list())
