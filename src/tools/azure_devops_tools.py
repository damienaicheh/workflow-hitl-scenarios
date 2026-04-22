import json
from typing import Annotated, Any

import aiohttp
from agent_framework import tool
from pydantic import Field

ADO_API_VERSION = "7.1"


class AzureDevOpsTools:
    """Azure DevOps Git operations via REST API (aiohttp).

    Based on Damien Aicheh's implementation with additions for
    branch creation, multi-file push, and pull request creation.
    """

    def __init__(self, organization: str, auth_token: str, default_project: str | None):
        self.organization = organization
        self.auth_token = auth_token
        self.default_project = default_project

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
                        f"Azure DevOps API returned {response.status} for {method} {url}: "
                        f"{detail or 'No response body.'}"
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
            self._build_url(project, f"/_apis/git/repositories/{repository_name}"),
            params={"api-version": ADO_API_VERSION},
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
            self._build_url(project, f"/_apis/git/repositories/{repository_id}/refs"),
            params={
                "filter": f"heads/{branch_name}",
                "api-version": ADO_API_VERSION,
            },
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
            self._build_url(project, f"/_apis/git/repositories/{repository_id}/items"),
            params={
                "path": path,
                "includeContentMetadata": "true",
                "versionDescriptor.version": branch_name,
                "versionDescriptor.versionType": "branch",
                "api-version": ADO_API_VERSION,
            },
            allow_404=True,
        )
        return response is not None

    # ── Tool: create or update a single file ─────────────────────────

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
            Field(description="Repository path for the file, for example '/docs/plan.md'."),
        ],
        content: Annotated[
            str,
            Field(description="Full UTF-8 text content to write into the file."),
        ],
        project: Annotated[
            str | None,
            Field(description="Azure DevOps project name. Uses ADO_DEFAULT_PROJECT when omitted."),
        ] = None,
        branch: Annotated[
            str | None,
            Field(description="Existing branch name. Uses the repository default branch when omitted."),
        ] = None,
        commit_message: Annotated[
            str | None,
            Field(description="Git commit message. A default message is generated when omitted."),
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
            resolved_project, repository_id, normalized_path, branch_name,
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

    # ── Tool: push multiple Terraform files to a new branch ──────────

    @tool(
        name="push_terraform_branch",
        description="Create a new branch from the default branch and push multiple Terraform files to it.",
        approval_mode="never_require",
    )
    async def push_terraform_branch(
        self,
        repository: Annotated[
            str,
            Field(description="Azure DevOps repository name."),
        ],
        branch_name: Annotated[
            str,
            Field(description="Name of the new branch to create (e.g. 'infra/add-app-service')."),
        ],
        terraform_files_json: Annotated[
            str,
            Field(description="JSON string: list of objects with 'filename' and 'content' keys."),
        ],
        commit_message: Annotated[
            str,
            Field(description="Commit message for the push."),
        ],
        project: Annotated[
            str | None,
            Field(description="Azure DevOps project name. Uses ADO_DEFAULT_PROJECT when omitted."),
        ] = None,
    ) -> str:
        resolved_project = self._resolve_project(project)
        repository_info = await self._resolve_repository(resolved_project, repository)
        repository_id = str(repository_info["id"])
        default_branch = self._default_branch_name(repository_info)

        # Get HEAD of the default branch
        default_ref = await self._resolve_branch_ref(
            resolved_project, repository_id, default_branch
        )
        old_object_id = default_ref["objectId"]

        # Create the new branch
        await self._request_json(
            "POST",
            self._build_url(
                resolved_project,
                f"/_apis/git/repositories/{repository_id}/refs",
            ),
            params={"api-version": ADO_API_VERSION},
            payload=[
                {
                    "name": f"refs/heads/{branch_name}",
                    "oldObjectId": "0" * 40,
                    "newObjectId": old_object_id,
                }
            ],
            expected_statuses=(200, 201),
        )

        # Build file changes
        files = json.loads(terraform_files_json)
        changes = []
        for f in files:
            path = f"/infra/{f['filename']}" if not f["filename"].startswith("/") else f["filename"]
            exists = await self._file_exists(
                resolved_project, repository_id, path, branch_name
            )
            changes.append(
                {
                    "changeType": "edit" if exists else "add",
                    "item": {"path": path},
                    "newContent": {"content": f["content"], "contentType": "rawtext"},
                }
            )

        # Push the commit
        await self._request_json(
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
                        "oldObjectId": old_object_id,
                    }
                ],
                "commits": [{"comment": commit_message, "changes": changes}],
            },
            expected_statuses=(200, 201),
        )

        return (
            f"Branch '{branch_name}' created and {len(files)} file(s) pushed "
            f"in project '{resolved_project}'."
        )

    # ── Tool: create a pull request ──────────────────────────────────

    @tool(
        name="create_pull_request",
        description="Create a Pull Request in Azure DevOps from a source branch to the default branch.",
        approval_mode="never_require",
    )
    async def create_pull_request(
        self,
        repository: Annotated[
            str,
            Field(description="Azure DevOps repository name."),
        ],
        branch_name: Annotated[
            str,
            Field(description="Source branch name."),
        ],
        title: Annotated[
            str,
            Field(description="PR title."),
        ],
        description: Annotated[
            str,
            Field(description="PR description in markdown."),
        ],
        project: Annotated[
            str | None,
            Field(description="Azure DevOps project name. Uses ADO_DEFAULT_PROJECT when omitted."),
        ] = None,
    ) -> str:
        resolved_project = self._resolve_project(project)
        repository_info = await self._resolve_repository(resolved_project, repository)
        repository_id = str(repository_info["id"])
        target_branch = self._default_branch_name(repository_info)

        response = await self._request_json(
            "POST",
            self._build_url(
                resolved_project,
                f"/_apis/git/repositories/{repository_id}/pullrequests",
            ),
            params={"api-version": ADO_API_VERSION},
            payload={
                "sourceRefName": f"refs/heads/{branch_name}",
                "targetRefName": f"refs/heads/{target_branch}",
                "title": title,
                "description": description,
            },
            expected_statuses=(200, 201),
        )

        pr_id = response["pullRequestId"]
        web_url = (
            f"https://dev.azure.com/{self.organization}/{resolved_project}"
            f"/_git/{repository_info.get('name', repository)}/pullrequest/{pr_id}"
        )
        return f"Pull Request #{pr_id} created: {web_url}"
