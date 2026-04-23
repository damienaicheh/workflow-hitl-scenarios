import base64
import json
from typing import Annotated, Any

import aiohttp
from agent_framework import MCPStdioTool, tool
from pydantic import Field

from utils.env import get_first_env, require_env

ADO_API_VERSION = "7.1"


class AzureDevOpsTools:
    def __init__(self, organization: str, auth_token: str, default_project: str | None):
        self.organization = organization
        self.auth_token = auth_token
        self.default_project = default_project


    def _resolve_ado_org(self) -> str:
        return require_env("ADO_ORG").removeprefix("https://dev.azure.com/").strip("/")


    def _resolve_pat_credential(self) -> str:
        raw_pat = get_first_env("ADO_PAT")
        if not raw_pat:
            raise ValueError("PAT auth requires ADO_PAT.")

        # Azure DevOps only uses the PAT portion of username:pat, so any non-empty placeholder works.
        pat_identity = "ado@example.invalid"
        return base64.b64encode(f"{pat_identity}:{raw_pat}".encode("utf-8")).decode("utf-8")


    def _resolve_ado_domains(self) -> list[str]:
        raw_domains = get_first_env("ADO_DOMAINS")
        if not raw_domains:
            return []

        return [domain.strip() for domain in raw_domains.split(",") if domain.strip()]


    def build_ado_mcp_tool(self) -> MCPStdioTool:
        tool_args = [
            "-y",
            "@azure-devops/mcp",
            self.resolve_ado_org(),
            "--authentication",
            "pat",
        ]

        for domain in self.resolve_ado_domains():
            tool_args.extend(["-d", domain])

        return MCPStdioTool(
            name="azure_devops",
            command="npx",
            args=tool_args,
            env={"PERSONAL_ACCESS_TOKEN": self.resolve_pat_credential()},
            load_prompts=False,
            approval_mode="never_require",
            description="Azure DevOps tools exposed through the local Azure DevOps MCP server.",
        )


    def _resolve_project(self, project: str | None) -> str:
        if project and project.strip():
            return project.strip()

        if self.default_project:
            return self.default_project

        raise ValueError(
            "Missing Azure DevOps project. Provide 'project' or set ADO_DEFAULT_PROJECT."
        )

    def _default_branch_name(self, repository: dict[str, Any]) -> str:
        default_branch = repository.get("defaultBranch")
        if isinstance(default_branch, str) and default_branch.strip():
            return default_branch.removeprefix("refs/heads/")

        return "main"

    def _normalize_branch_name(self, branch: str) -> str:
        cleaned_branch = branch.strip()
        return cleaned_branch.removeprefix("refs/heads/")

    def _normalize_repo_path(self, path: str) -> str:
        cleaned_path = path.strip()
        if not cleaned_path:
            raise ValueError("File path cannot be empty.")

        return cleaned_path if cleaned_path.startswith("/") else f"/{cleaned_path}"

    def _build_url(self, project: str, suffix: str) -> str:
        return f"https://dev.azure.com/{self.organization}/{project}{suffix}"

    async def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        expected_statuses: tuple[int, ...] = (200,),
        allow_404: bool = False,
    ) -> dict[str, Any] | None:
        headers = {
            "Authorization": f"Basic {self.auth_token}",
            "Accept": "application/json",
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.request(
                method, url, params=params, json=payload
            ) as response:
                response_text = await response.text()

                if allow_404 and response.status == 404:
                    return None

                if response.status not in expected_statuses:
                    detail = response_text.strip()
                    raise ValueError(
                        f"Azure DevOps API returned {response.status} for {method} {url}: {detail or 'No response body.'}"
                    )

                if not response_text.strip():
                    return None

                try:
                    return json.loads(response_text)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"Azure DevOps API returned invalid JSON for {method} {url}: {error}"
                    ) from error

    async def _resolve_repository(
        self, project: str, repository: str
    ) -> dict[str, Any]:
        repository_name = repository.strip()
        if not repository_name:
            raise ValueError("Repository cannot be empty.")

        response = await self._request_json(
            "GET",
            self._build_url(
                project,
                f"/_apis/git/repositories/{repository_name}",
            ),
            params={"api-version": ADO_API_VERSION},
            expected_statuses=(200,),
        )

        if not response:
            raise ValueError(f"Repository '{repository_name}' was not found.")

        return response

    async def _resolve_branch_ref(
        self, project: str, repository_id: str, branch: str
    ) -> dict[str, Any]:
        branch_name = self._normalize_branch_name(branch)
        response = await self._request_json(
            "GET",
            self._build_url(
                project,
                f"/_apis/git/repositories/{repository_id}/refs",
            ),
            params={
                "filter": f"heads/{branch_name}",
                "api-version": ADO_API_VERSION,
            },
            expected_statuses=(200,),
        )

        refs = response.get("value", []) if response else []
        ref_name = f"refs/heads/{branch_name}"
        for ref in refs:
            if ref.get("name") == ref_name:
                return ref

        raise ValueError(
            f"Branch '{branch_name}' was not found in repository '{repository_id}'."
        )

    async def _file_exists(
        self, project: str, repository_id: str, path: str, branch: str
    ) -> bool:
        branch_name = self._normalize_branch_name(branch)
        response = await self._request_json(
            "GET",
            self._build_url(
                project,
                f"/_apis/git/repositories/{repository_id}/items",
            ),
            params={
                "path": path,
                "includeContentMetadata": "true",
                "versionDescriptor.version": branch_name,
                "versionDescriptor.versionType": "branch",
                "api-version": ADO_API_VERSION,
            },
            expected_statuses=(200,),
            allow_404=True,
        )
        return response is not None

    @tool(
        name="create_file_in_repo",
        description="Create or update a UTF-8 text file in an Azure DevOps Git repository on an existing branch.",
        approval_mode="never_require",
    )
    async def create_file_in_repo(
        self,
        repository: Annotated[
            str,
            Field(description="Azure DevOps repository name or repository ID."),
        ],
        path: Annotated[
            str,
            Field(
                description="Repository path for the file, for example '/docs/plan.md'."
            ),
        ],
        content: Annotated[
            str,
            Field(description="Full UTF-8 text content to write into the file."),
        ],
        project: Annotated[
            str | None,
            Field(
                description="Azure DevOps project name. Uses ADO_DEFAULT_PROJECT when omitted."
            ),
        ] = None,
        branch: Annotated[
            str | None,
            Field(
                description="Existing branch name. Uses the repository default branch when omitted."
            ),
        ] = None,
        commit_message: Annotated[
            str | None,
            Field(
                description="Git commit message. A default message is generated when omitted."
            ),
        ] = None,
    ) -> str:
        resolved_project = self._resolve_project(project)
        repository_info = await self._resolve_repository(resolved_project, repository)
        repository_id = str(repository_info["id"])
        repository_name = str(repository_info.get("name") or repository)

        branch_name = self._normalize_branch_name(
            branch or self._default_branch_name(repository_info)
        )
        normalized_path = self._normalize_repo_path(path)
        branch_ref = await self._resolve_branch_ref(
            resolved_project, repository_id, branch_name
        )
        file_exists = await self._file_exists(
            resolved_project,
            repository_id,
            normalized_path,
            branch_name,
        )
        change_type = "edit" if file_exists else "add"
        comment = commit_message or (
            f"{'Update' if file_exists else 'Create'} {normalized_path}"
        )

        push_response = await self._request_json(
            "POST",
            self._build_url(
                resolved_project,
                f"/_apis/git/repositories/{repository_id}/pushes",
            ),
            params={"api-version": ADO_API_VERSION},
            payload={
                "refUpdates": [
                    {
                        "name": f"refs/heads/{branch_name}",
                        "oldObjectId": branch_ref["objectId"],
                    }
                ],
                "commits": [
                    {
                        "comment": comment,
                        "changes": [
                            {
                                "changeType": change_type,
                                "item": {"path": normalized_path},
                                "newContent": {
                                    "content": content,
                                    "contentType": "rawtext",
                                },
                            }
                        ],
                    }
                ],
            },
            expected_statuses=(200, 201),
        )

        commits = push_response.get("commits", []) if push_response else []
        commit_id = commits[0].get("commitId") if commits else None
        action = "updated" if file_exists else "created"
        result = (
            f"File '{normalized_path}' {action} in repository '{repository_name}' "
            f"on branch '{branch_name}' in project '{resolved_project}'."
        )
        if commit_id:
            result += f" Commit: {commit_id}."

        return result