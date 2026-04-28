from pydantic import BaseModel, Field


class AdoConfig(BaseModel):
    """Azure DevOps configuration."""

    organisation: str = Field(description="Azure DevOps organization name")
    personal_access_token: str = Field(description="Azure DevOps personal access token")
    default_project: str = Field(description="Default Azure DevOps project name")
    repository: str = Field(description="Azure DevOps repository name")
