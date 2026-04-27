from dataclasses import dataclass


@dataclass
class ReviewerApprovalRequest:
    """Sent to the human for review of generated Terraform."""

    terraform_json: str
    summary: str
    prompt: str
    publisher_result_payload: dict[str, object]
