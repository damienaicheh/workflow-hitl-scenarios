import os
from typing import Annotated, Any

import aiohttp
from agent_framework import tool


class WorkflowHttpTools:
    """HTTP tools used by the orchestrator agent.

    Each tool is an Azure Function HTTP endpoint exposed by the workflow
    (AgentFunctionApp). The orchestrator agent invokes them over HTTP so that
    the workflow can be driven from anywhere, including from a Teams bot.
    """

    def __init__(self) -> None:
        self._base_url = os.environ["WORKFLOW_API_BASE_URL"]
        self._headers = {
            "x-functions-key": os.environ["WORKFLOW_API_FUNCTION_KEY"],
        }

    async def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        allow_empty_response: bool = False,
    ) -> dict[str, Any]:
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.request(
                method,
                f"{self._base_url}{path}",
                json=payload,
            ) as response:
                response.raise_for_status()
                if allow_empty_response:
                    try:
                        return await response.json()
                    except Exception:
                        return {}
                return await response.json()

    @tool(
        name="trigger_infra_workflow",
        description="Trigger a new IaC creation workflow and return the workflow instance ID.",
    )
    async def trigger_workflow(
        self,
        service: Annotated[
            str, "The azure service to deploy (e.g. 'App Service', 'Storage Account')."
        ],
        region: Annotated[
            str, "The Azure region to deploy the service to (e.g. 'westeurope')."
        ],
        options: Annotated[str, "Free text describing SKU, tier, extra features."],
    ) -> dict[str, Any]:
        """Start a new IaC deployment workflow.

        Args:
            service: Azure service to deploy (e.g. "App Service", "Storage Account").
            region: Azure region (e.g. "westeurope").
            options: Free text describing SKU, tier, extra features.
            recipient_email: Email address that receives the deployment summary.

        Returns:
            A dict with the created ``instance_id``.
        """
        payload = {
            "service": service,
            "region": region,
            "options": options,
        }
        data = await self._request_json("POST", "/api/workflow/run", payload)
        instance_id = data.get("instanceId")
        if not instance_id:
            raise RuntimeError("Workflow backend did not return an instance ID.")
        return {"instance_id": instance_id}

    @tool(
        name="get_workflow_status",
        description="Get the current status of a running IaC workflow given its instance ID.",
    )
    async def get_workflow_status(
        self,
        instance_id: Annotated[
            str, "The workflow instance identifier returned by trigger_workflow."
        ],
    ) -> dict[str, Any]:
        """Return the current status of a running IaC workflow.

        Args:
            instance_id: The workflow instance identifier returned by trigger_workflow.
        """
        return await self._request_json("GET", f"/api/workflow/status/{instance_id}")
