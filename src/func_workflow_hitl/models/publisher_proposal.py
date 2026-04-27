from pydantic import BaseModel


class PublisherProposal(BaseModel):
    branch_name: str
    pull_request_title: str
    pull_request_description: str
