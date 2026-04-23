from dataclasses import dataclass


@dataclass
class ReviewerApprovalResponse:
    """Human response: approve or reject with feedback."""

    approved: bool
    feedback: str | None = None
