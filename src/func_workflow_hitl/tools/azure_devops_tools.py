import base64
import json
from typing import Annotated, Any

import aiohttp
from agent_framework import tool
from pydantic import Field

ADO_API_VERSION = "7.1"


class AzureDevOpsTools:
    """Azure DevOps Git operations via REST API and the local MCP server."""

    def __init__(
        self,
        organization: str,
        auth_token: str,
        default_project: str | None,
        default_repository: str | None = None,
    ):
        self.organization = self._normalize_organization(organization)
        self.auth_token = self._encode_pat(auth_token)
        self.default_project = default_project
        self.default_repository = (
            default_repository.strip() if default_repository else None
        )

    def _normalize_organization(self, organization: str) -> str:
        cleaned_organization = organization.removeprefix(
            "https://dev.azure.com/"
        ).strip("/")
        if not cleaned_organization:
            raise ValueError("Azure DevOps organization cannot be empty.")

        return cleaned_organization

    def _encode_pat(self, personal_access_token: str) -> str:
        cleaned_pat = personal_access_token.strip()
        if not cleaned_pat:
            raise ValueError("Azure DevOps PAT cannot be empty.")

        # Azure DevOps only uses the PAT portion of username:pat, so any non-empty placeholder works.
        pat_identity = "ado@example.invalid"
        return base64.b64encode(f"{pat_identity}:{cleaned_pat}".encode("utf-8")).decode(
            "utf-8"
        )

    def _resolve_project(self, project: str | None) -> str:
        if project and project.strip():
            return project.strip()

        if self.default_project:
            return self.default_project

        raise ValueError(
            "Missing Azure DevOps project. Provide 'project' or set ADO_DEFAULT_PROJECT."
        )

    def _resolve_repository_name(self, repository: str | None = None) -> str:
        if repository and repository.strip():
            return repository.strip()

        if self.default_repository:
            return self.default_repository

        raise ValueError(
            "Missing Azure DevOps repository. Provide 'repository' or set a default repository."
        )

    def _default_branch_name(self, repository: dict[str, Any]) -> str:
        default_branch = repository.get("defaultBranch")
        if isinstance(default_branch, str) and default_branch.strip():
            return default_branch.removeprefix("refs/heads/")

        return "main"

    def _normalize_branch_name(self, branch: str) -> str:
        cleaned_branch = branch.strip()
        return cleaned_branch.removeprefix("refs/heads/")

    def _pull_request_web_url(
        self,
        project: str,
        repository_name: str,
        pull_request_id: int,
    ) -> str:
        return (
            f"https://dev.azure.com/{self.organization}/{project}"
            f"/_git/{repository_name}/pullrequest/{pull_request_id}"
        )

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
        payload: dict[str, Any] | list[dict[str, Any]] | None = None,
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

    async def _find_branch_ref(
        self, project: str, repository_id: str, branch: str
    ) -> dict[str, Any] | None:
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

        return None

    async def _resolve_branch_ref(
        self, project: str, repository_id: str, branch: str
    ) -> dict[str, Any]:
        branch_name = self._normalize_branch_name(branch)
        ref = await self._find_branch_ref(project, repository_id, branch_name)
        if ref is not None:
            return ref

        raise ValueError(
            f"Branch '{branch_name}' was not found in repository '{repository_id}'."
        )

    async def _next_available_branch_name(
        self, project: str, repository_id: str, branch: str
    ) -> str:
        normalized_branch_name = self._normalize_branch_name(branch)
        if (
            await self._find_branch_ref(
                project,
                repository_id,
                normalized_branch_name,
            )
            is None
        ):
            return normalized_branch_name

        suffix = 2
        while True:
            candidate_branch_name = f"{normalized_branch_name}-{suffix}"
            if (
                await self._find_branch_ref(
                    project,
                    repository_id,
                    candidate_branch_name,
                )
                is None
            ):
                return candidate_branch_name

            suffix += 1

    @tool(
        name="create_branch",
        description="Create a new Azure DevOps Git branch and return the actual created branch details.",
        approval_mode="never_require",
    )
    async def create_branch(
        self,
        branch_name: Annotated[
            str,
            Field(
                description="Requested source branch name, for example 'infra/add-networking'."
            ),
        ],
        project: Annotated[
            str | None,
            Field(
                description="Azure DevOps project name. Uses ADO_DEFAULT_PROJECT when omitted."
            ),
        ] = None,
        base_branch: Annotated[
            str | None,
            Field(
                description="Base branch name. Uses the repository default branch when omitted."
            ),
        ] = None,
        repository: Annotated[
            str | None,
            Field(
                description="Azure DevOps repository name or repository ID. Uses the configured default repository when omitted."
            ),
        ] = None,
    ) -> dict[str, Any]:
        resolved_repository = self._resolve_repository_name(repository)
        resolved_project = self._resolve_project(project)
        repository_info = await self._resolve_repository(
            resolved_project, resolved_repository
        )
        repository_id = str(repository_info["id"])
        repository_name = str(repository_info.get("name") or resolved_repository)
        normalized_branch_name = self._normalize_branch_name(branch_name)
        normalized_base_branch = self._normalize_branch_name(
            base_branch or self._default_branch_name(repository_info)
        )

        default_ref = await self._resolve_branch_ref(
            resolved_project,
            repository_id,
            normalized_base_branch,
        )
        old_object_id = str(default_ref["objectId"])

        candidate_branch_name = await self._next_available_branch_name(
            resolved_project,
            repository_id,
            normalized_branch_name,
        )

        for _ in range(10):
            response = await self._request_json(
                "POST",
                self._build_url(
                    resolved_project,
                    f"/_apis/git/repositories/{repository_id}/refs",
                ),
                params={"api-version": ADO_API_VERSION},
                payload=[
                    {
                        "name": f"refs/heads/{candidate_branch_name}",
                        "oldObjectId": "0" * 40,
                        "newObjectId": old_object_id,
                    }
                ],
                expected_statuses=(200, 201),
            )

            results = response.get("value", []) if response else []
            if not results:
                raise ValueError(
                    f"Azure DevOps did not return a branch creation result for '{candidate_branch_name}'."
                )

            result = results[0]
            if result.get("success"):
                return {
                    "branch_name": candidate_branch_name,
                    "base_branch": normalized_base_branch,
                    "project": resolved_project,
                    "repository": repository_name,
                    "head_commit_id": old_object_id,
                }

            update_status = result.get("updateStatus") or "unknown"
            if update_status == "staleOldObjectId":
                candidate_branch_name = await self._next_available_branch_name(
                    resolved_project,
                    repository_id,
                    normalized_branch_name,
                )
                continue

            custom_message = result.get("customMessage")
            detail = (
                f"{update_status}: {custom_message}"
                if custom_message
                else update_status
            )
            raise ValueError(
                f"Failed to create branch '{candidate_branch_name}' in repository '{repository_name}': {detail}"
            )

        raise ValueError(
            f"Failed to create a unique branch for '{normalized_branch_name}' in repository '{repository_name}' after repeated collisions."
        )

    @tool(
        name="create_pull_request",
        description="Create an Azure DevOps pull request from an existing source branch.",
        approval_mode="never_require",
    )
    async def create_pull_request(
        self,
        branch_name: Annotated[
            str,
            Field(description="Existing source branch name for the pull request."),
        ],
        title: Annotated[
            str,
            Field(description="Pull request title."),
        ],
        description: Annotated[
            str,
            Field(description="Pull request description."),
        ],
        project: Annotated[
            str | None,
            Field(
                description="Azure DevOps project name. Uses ADO_DEFAULT_PROJECT when omitted."
            ),
        ] = None,
        target_branch: Annotated[
            str | None,
            Field(
                description="Target branch name. Uses the repository default branch when omitted."
            ),
        ] = None,
        repository: Annotated[
            str | None,
            Field(
                description="Azure DevOps repository name or repository ID. Uses the configured default repository when omitted."
            ),
        ] = None,
    ) -> dict[str, Any]:
        resolved_repository = self._resolve_repository_name(repository)
        resolved_project = self._resolve_project(project)
        repository_info = await self._resolve_repository(
            resolved_project, resolved_repository
        )
        repository_id = str(repository_info["id"])
        repository_name = str(repository_info.get("name") or resolved_repository)
        normalized_branch_name = self._normalize_branch_name(branch_name)
        normalized_target_branch = self._normalize_branch_name(
            target_branch or self._default_branch_name(repository_info)
        )

        response = await self._request_json(
            "POST",
            self._build_url(
                resolved_project,
                f"/_apis/git/repositories/{repository_id}/pullrequests",
            ),
            params={"api-version": ADO_API_VERSION},
            payload={
                "sourceRefName": f"refs/heads/{normalized_branch_name}",
                "targetRefName": f"refs/heads/{normalized_target_branch}",
                "title": title,
                "description": description,
            },
            expected_statuses=(200, 201),
        )

        if not response:
            raise ValueError(
                f"Azure DevOps did not return a pull request response for branch '{normalized_branch_name}'."
            )

        pull_request_id = response.get("pullRequestId")
        if not isinstance(pull_request_id, int):
            raise ValueError(
                f"Azure DevOps returned an invalid pull request identifier for branch '{normalized_branch_name}'."
            )

        return {
            "pull_request_id": pull_request_id,
            "pull_request_url": self._pull_request_web_url(
                resolved_project,
                repository_name,
                pull_request_id,
            ),
            "source_branch": normalized_branch_name,
            "target_branch": normalized_target_branch,
            "title": title,
            "status": response.get("status"),
        }

    @tool(
        name="get_pull_request",
        description="Fetch an Azure DevOps pull request by identifier.",
        approval_mode="never_require",
    )
    async def get_pull_request(
        self,
        pull_request_id: Annotated[
            int,
            Field(description="Azure DevOps pull request identifier."),
        ],
        project: Annotated[
            str | None,
            Field(
                description="Azure DevOps project name. Uses ADO_DEFAULT_PROJECT when omitted."
            ),
        ] = None,
        repository: Annotated[
            str | None,
            Field(
                description="Azure DevOps repository name or repository ID. Uses the configured default repository when omitted."
            ),
        ] = None,
    ) -> dict[str, Any]:
        resolved_repository = self._resolve_repository_name(repository)
        resolved_project = self._resolve_project(project)
        repository_info = await self._resolve_repository(
            resolved_project, resolved_repository
        )
        repository_id = str(repository_info["id"])

        response = await self._request_json(
            "GET",
            self._build_url(
                resolved_project,
                f"/_apis/git/repositories/{repository_id}/pullrequests/{pull_request_id}",
            ),
            params={"api-version": ADO_API_VERSION},
            expected_statuses=(200,),
        )

        if not response:
            raise ValueError(
                f"Azure DevOps did not return pull request '{pull_request_id}'."
            )

        return response

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
        repository: Annotated[
            str | None,
            Field(
                description="Azure DevOps repository name or repository ID. Uses the configured default repository when omitted."
            ),
        ] = None,
    ) -> str:
        resolved_repository = self._resolve_repository_name(repository)
        resolved_project = self._resolve_project(project)
        repository_info = await self._resolve_repository(
            resolved_project, resolved_repository
        )
        repository_id = str(repository_info["id"])
        repository_name = str(repository_info.get("name") or resolved_repository)

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

    @tool(
        name="push_files_to_branch",
        description="Push multiple files to an existing Azure DevOps branch.",
        approval_mode="never_require",
    )
    async def push_files_to_branch(
        self,
        branch_name: Annotated[
            str,
            Field(
                description="Existing branch name to update, for example 'infra/add-app-service'."
            ),
        ],
        terraform_files_json: Annotated[
            str,
            Field(
                description="JSON string containing a list of objects with either 'path' or 'filename', plus 'content'."
            ),
        ],
        commit_message: Annotated[
            str,
            Field(description="Commit message for the push."),
        ],
        project: Annotated[
            str | None,
            Field(
                description="Azure DevOps project name. Uses ADO_DEFAULT_PROJECT when omitted."
            ),
        ] = None,
        repository: Annotated[
            str | None,
            Field(
                description="Azure DevOps repository name. Uses the configured default repository when omitted."
            ),
        ] = None,
    ) -> str:
        resolved_repository = self._resolve_repository_name(repository)
        resolved_project = self._resolve_project(project)
        repository_info = await self._resolve_repository(
            resolved_project, resolved_repository
        )
        repository_id = str(repository_info["id"])
        normalized_branch_name = self._normalize_branch_name(branch_name)

        branch_ref = await self._resolve_branch_ref(
            resolved_project,
            repository_id,
            normalized_branch_name,
        )

        files = json.loads(terraform_files_json)
        if not isinstance(files, list):
            raise ValueError("terraform_files_json must decode to a list of files.")

        changes: list[dict[str, Any]] = []
        for file_data in files:
            if not isinstance(file_data, dict):
                raise ValueError("Each Terraform file entry must be an object.")

            path = file_data.get("path")
            filename = file_data.get("filename")
            content = file_data.get("content")
            if not isinstance(content, str):
                raise ValueError(
                    "Each Terraform file entry must include a string 'content' field."
                )

            if isinstance(path, str):
                normalized_path = self._normalize_repo_path(path)
            elif isinstance(filename, str):
                normalized_path = self._normalize_repo_path(
                    filename if filename.startswith("/") else f"/infra/{filename}"
                )
            else:
                raise ValueError(
                    "Each Terraform file entry must include a string 'path' or 'filename' field."
                )

            exists = await self._file_exists(
                resolved_project,
                repository_id,
                normalized_path,
                normalized_branch_name,
            )
            changes.append(
                {
                    "changeType": "edit" if exists else "add",
                    "item": {"path": normalized_path},
                    "newContent": {"content": content, "contentType": "rawtext"},
                }
            )

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
                        "name": f"refs/heads/{normalized_branch_name}",
                        "oldObjectId": branch_ref["objectId"],
                    }
                ],
                "commits": [{"comment": commit_message, "changes": changes}],
            },
            expected_statuses=(200, 201),
        )

        return (
            f"Branch '{normalized_branch_name}' updated with {len(files)} file(s) "
            f"in project '{resolved_project}'."
        )
