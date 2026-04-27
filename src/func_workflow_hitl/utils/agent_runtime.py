from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from agent_framework import Agent


@asynccontextmanager
async def managed_agent(agent: Agent) -> AsyncIterator[Agent]:
    """Reuse executor-scoped agents without tearing down shared clients per call."""
    async with agent:
        yield agent
