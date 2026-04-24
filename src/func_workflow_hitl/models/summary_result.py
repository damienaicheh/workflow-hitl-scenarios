from models.publisher_result import PublisherResult
from pydantic import BaseModel, Field


class SummaryResult(BaseModel):
    publisher_result: PublisherResult = Field(
        description="Publication outcome (branch name, pull request id and URL)."
    )
    email_sent_to: str = Field(description="Recipient email address.")
    email_subject: str = Field(description="Subject line sent to the recipient.")
