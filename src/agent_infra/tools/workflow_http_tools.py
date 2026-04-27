import os
from typing import Any

import aiohttp


class WorkflowHttpTools:
    """HTTP tools used by the orchestrator agent.

    Each tool is an Azure Function HTTP endpoint exposed by the workflow
    (AgentFunctionApp). The orchestrator agent invokes them over HTTP so that
    the workflow can be driven from anywhere, including from a Teams bot.
    """

    def __init__(self) -> None:
        self._base_url = (os.environ["WORKFLOW_API_BASE_URL"]).rstrip("/")

    async def trigger_workflow(
        self,
        service: str,
        region: str,
        options: str,
        recipient_email: str,
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
            "recipient_email": recipient_email,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/api/workflow/run",
                json=payload,
            ) as response:
                response.raise_for_status()
                data = await response.json()
        return {"instance_id": data.get("instanceId") or data.get("instance_id")}

    async def get_workflow_status(self, instance_id: str) -> dict[str, Any]:
        """Return the current status of a running IaC workflow.

        Args:
            instance_id: The workflow instance identifier returned by trigger_workflow.
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self._base_url}/api/workflow/status/{instance_id}"
            ) as response:
                response.raise_for_status()
                return await response.json()

    async def respond_to_review(
        self,
        instance_id: str,
        approved: bool,
        feedback: str,
    ) -> dict[str, Any]:
        """Respond to the human-in-the-loop review step of a workflow.

        Call this only when the user has explicitly approved or rejected the
        Terraform review. On rejection, ``feedback`` must contain the changes
        requested by the user so the drafter can redraft.

        Args:
            instance_id: The workflow instance identifier.
            approved: True to approve the Terraform review, False to reject.
            feedback: Free text feedback from the user (required on rejection,
                optional but recommended on approval).
        """
        status = await self.get_workflow_status(instance_id)
        pending = status.get("pendingHumanInputRequests") or []
        if not pending:
            return {
                "accepted": False,
                "reason": "No pending human input request for this workflow.",
                "runtime_status": status.get("runtimeStatus"),
            }
        request_id = pending[0].get("requestId") or pending[0].get("request_id")

        payload = {"approved": approved, "feedback": feedback}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/api/workflow/respond/{instance_id}/{request_id}",
                json=payload,
            ) as response:
                response.raise_for_status()
                try:
                    body = await response.json()
                except Exception:
                    body = {}
        return {"accepted": True, "request_id": request_id, "response": body}
