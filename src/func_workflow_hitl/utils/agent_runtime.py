from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from inspect import isawaitable
from typing import Any

from agent_framework import Agent


async def _close_resource(resource: Any | None) -> bool:
    if resource is None:
        return False

    close = getattr(resource, "close", None)
    if not callable(close):
        return False

    result = close()
    if isawaitable(result):
        await result

    return True


async def _close_agent_client(agent: Agent) -> None:
    client = getattr(agent, "client", None)
    if client is None or isinstance(client, AbstractAsyncContextManager):
        return

    await _close_resource(getattr(client, "client", None))
    await _close_resource(getattr(client, "project_client", None))
    await _close_resource(client)


@asynccontextmanager
async def managed_agent(agent: Agent) -> AsyncIterator[Agent]:
    async with agent:
        yield agent

    await _close_agent_client(agent)
