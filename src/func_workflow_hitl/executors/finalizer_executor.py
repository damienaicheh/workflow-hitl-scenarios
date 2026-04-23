from agent_framework import (
    Agent,
    Executor,
    WorkflowContext,
    handler,
)
from typing_extensions import Never
from utils.response_format import extract_response_text


class FinalizerExecutor(Executor):
    def __init__(self, agent: Agent) -> None:
        super().__init__(id="finalizer_executor")
        self._agent = agent

    @handler
    async def finalize(
        self,
        edited_text: str,
        ctx: WorkflowContext[Never, str],
    ) -> None:
        response = await self._agent.run(
            "Create a polished final version of the text below. Return only the final version.\n\n"
            f"Edited draft:\n{edited_text}"
        )
        await ctx.yield_output(extract_response_text(response))
