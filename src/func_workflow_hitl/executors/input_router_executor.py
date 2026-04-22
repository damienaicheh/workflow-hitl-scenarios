import json
from typing import Any

from agent_framework import (
    Executor,
    WorkflowContext,
    handler,
)


class InputRouterExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(id="input_router")

    def _extract_prompt(self, input_data: Any) -> str:
        if isinstance(input_data, str):
            prompt = input_data.strip()
            if prompt:
                return prompt
        elif isinstance(input_data, dict):
            message = input_data.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()

            title = input_data.get("title")
            body = input_data.get("body")
            if any(isinstance(value, str) and value.strip() for value in (title, body)):
                payload = {
                    "title": title or "Untitled",
                    "body": body or "",
                }
                return (
                    "Create a brief draft from the following source material.\n\n"
                    f"Title: {payload['title']}\n"
                    f"Source:\n{payload['body']}"
                )

            return json.dumps(input_data, ensure_ascii=True)

        raise ValueError("Workflow input must be a non-empty string or a JSON object.")

    @handler
    async def route_input(self, input_data: Any, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(self._extract_prompt(input_data))
