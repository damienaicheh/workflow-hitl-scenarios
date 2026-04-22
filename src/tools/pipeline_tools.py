import json
from typing import Annotated, Any

import aiohttp
from agent_framework import tool
from pydantic import Field

ADO_API_VERSION = "7.1"


class PipelineTools:
    """Monitor Azure DevOps pipelines via REST API."""

    def __init__(self, organization: str, auth_token: str, default_project: str | None):
        self.organization = organization
        self.auth_token = auth_token
        self.default_project = default_project

    def _resolve_project(self, project: str | None) -> str:
        if project and project.strip():
            return project.strip()
        if self.default_project:
            return self.default_project
        raise ValueError("Missing Azure DevOps project.")

    def _build_url(self, project: str, suffix: str) -> str:
        return f"https://dev.azure.com/{self.organization}/{project}{suffix}"

    async def _request_json(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        headers = {
            "Authorization": f"Basic {self.auth_token}",
            "Accept": "application/json",
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.request(method, url, params=params) as response:
                text = await response.text()
                if response.status != 200:
                    raise ValueError(f"API returned {response.status}: {text}")
                return json.loads(text) if text.strip() else None

    @tool(
        name="get_pipeline_runs",
        description="List recent pipeline runs for a given pipeline in Azure DevOps.",
        approval_mode="never_require",
    )
    async def get_pipeline_runs(
        self,
        pipeline_id: Annotated[
            int,
            Field(description="Numeric pipeline ID."),
        ],
        top: Annotated[
            int,
            Field(description="Number of recent runs to retrieve."),
        ] = 5,
        project: Annotated[
            str | None,
            Field(description="Azure DevOps project name."),
        ] = None,
    ) -> str:
        resolved_project = self._resolve_project(project)
        response = await self._request_json(
            "GET",
            self._build_url(
                resolved_project,
                f"/_apis/pipelines/{pipeline_id}/runs",
            ),
            params={"$top": str(top), "api-version": ADO_API_VERSION},
        )
        runs = response.get("value", []) if response else []
        results = []
        for run in runs:
            results.append({
                "id": run.get("id"),
                "state": run.get("state"),
                "result": run.get("result"),
                "createdDate": run.get("createdDate"),
                "name": run.get("name"),
            })
        return json.dumps(results)

    @tool(
        name="get_pipeline_run_status",
        description="Get the status of a specific pipeline run.",
        approval_mode="never_require",
    )
    async def get_pipeline_run_status(
        self,
        pipeline_id: Annotated[
            int,
            Field(description="Numeric pipeline ID."),
        ],
        run_id: Annotated[
            int,
            Field(description="Numeric run ID."),
        ],
        project: Annotated[
            str | None,
            Field(description="Azure DevOps project name."),
        ] = None,
    ) -> str:
        resolved_project = self._resolve_project(project)
        response = await self._request_json(
            "GET",
            self._build_url(
                resolved_project,
                f"/_apis/pipelines/{pipeline_id}/runs/{run_id}",
            ),
            params={"api-version": ADO_API_VERSION},
        )
        if not response:
            return "Run not found."
        return json.dumps({
            "id": response.get("id"),
            "state": response.get("state"),
            "result": response.get("result"),
            "createdDate": response.get("createdDate"),
            "finishedDate": response.get("finishedDate"),
            "name": response.get("name"),
        })
