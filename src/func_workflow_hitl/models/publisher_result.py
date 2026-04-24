from pydantic import BaseModel, Field


class PublisherResult(BaseModel):
    branch_name: str = Field(description="Created Azure DevOps source branch name.")
    pull_request_id: int = Field(description="Azure DevOps pull request identifier.")
    pull_request_url: str = Field(
        description="Azure DevOps web URL for the created pull request."
    )
