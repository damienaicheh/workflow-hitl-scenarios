from dataclasses import dataclass


@dataclass
class ReviewerNotification:
    """Payload handed to the notifier so it can email the human an approval link.

    Carries the ``request_id`` the reviewer passed to ``ctx.request_info`` so the
    notifier addresses the exact pending request the workflow is waiting on, plus the
    pull request details to include in the email body.
    """

    request_id: str
    summary: str
    pull_request_id: int
    pull_request_url: str
