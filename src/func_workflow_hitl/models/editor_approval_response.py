from dataclasses import dataclass


@dataclass
class EditorApprovalResponse:
    approved: bool
    feedback: str | None = None
