from agent_framework import (
    Agent,
    Executor,
    WorkflowContext,
    handler,
)
from utils.response_format import extract_response_text


class DrafterExecutor(Executor):
    """Generate Terraform files from a natural-language infrastructure request."""

    def __init__(self, agent: Agent) -> None:
        super().__init__(id="drafter_executor")
        self._agent = agent

    @handler
    async def draft(
        self,
        prompt: str,
        ctx: WorkflowContext[str],
    ) -> None:
        instruction = (
            "Generate the Terraform .tf files for the following Azure "
            "infrastructure request. Output them as a JSON list: "
            '[{"filename": "main.tf", "content": "..."}, ...]. '
            "Follow Azure best practices and use azurerm provider.\n\n"
            f"Request:\n{prompt}"
        )
        response = await self._agent.run(instruction)
        await ctx.send_message(extract_response_text(response))
