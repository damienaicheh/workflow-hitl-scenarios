import json

from agent_framework import (
    Executor,
    WorkflowContext,
    handler,
)
from pydantic import BaseModel, Field


class InfraRequest(BaseModel):
    """Structured input for an Azure infrastructure deployment request."""

    service: str = Field(description="Azure service to deploy (e.g. App Service, AKS, Storage Account)")
    region: str = Field(description="Azure region (e.g. westeurope, francecentral)")
    options: str | None = Field(default=None, description="Additional options: SKU, tier, features, etc.")


class InputRouterExecutor(Executor):
    """Parse the incoming JSON request and build a prompt for the drafter."""

    def __init__(self) -> None:
        super().__init__(id="input_router")

    @handler
    async def route_input(self, input_data: str, ctx: WorkflowContext[str]) -> None:
        data = json.loads(input_data) if isinstance(input_data, str) else input_data
        request = InfraRequest.model_validate(data)

        prompt = (
            f"Deploy an Azure {request.service} in {request.region}."
        )
        if request.options:
            prompt += f" Additional requirements: {request.options}"

        await ctx.send_message(prompt)