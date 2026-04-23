from agent_framework import (
    Agent,
    Executor,
    WorkflowContext,
    handler,
)
from utils.response_format import extract_response_text


class DrafterExecutor(Executor):
    def __init__(self, agent: Agent) -> None:
        super().__init__(id="drafter_executor")
        self._agent = agent

    @handler
    async def draft(
        self,
        prompt: str,
        ctx: WorkflowContext[str],
    ) -> None:
        response = await self._agent.run(prompt)
        await ctx.send_message(extract_response_text(response))
