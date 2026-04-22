from dataclasses import dataclass


@dataclass
class EditorApprovalRequest:
    draft: str
    proposed_text: str
    prompt: str
