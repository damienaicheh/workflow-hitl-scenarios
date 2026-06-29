import logging

from agent_framework import Executor, WorkflowContext, handler
from agent_framework_azurefunctions import WorkflowHitlContext
from models.reviewer_notification import ReviewerNotification
from tools.email_tools import AcsEmailTools
from typing_extensions import Never
from utils.env import require_env

logger = logging.getLogger(__name__)


class NotifyExecutor(Executor):
    """Email the human reviewer a direct approve/reject link when the workflow pauses.

    Reached by an edge from ``ReviewerExecutor`` in the same superstep that raises the
    ``request_info`` approval request. It builds the canonical respond URL with
    :class:`WorkflowHitlContext` and emails it, so the reviewer clicks straight through
    instead of polling the status endpoint to discover the instance id and request id.

    Because it runs as a separate durable activity downstream of the executor that
    generated the request id, the id it emails is always the one the orchestration ends
    up waiting on, so a retried reviewer never emails a dead link.
    """

    def __init__(self) -> None:
        super().__init__(id="notify_executor")
        self._email_tools = AcsEmailTools()

    @handler
    async def notify(
        self,
        notification: ReviewerNotification,
        ctx: WorkflowContext[Never],
    ) -> None:
        hitl = WorkflowHitlContext.from_context(ctx)
        if hitl is None:
            # Not running on the Azure Functions durable host (e.g. in-process tests):
            # there is no respond endpoint to address, so skip the notification.
            logger.info("Not on the durable host; skipping reviewer notification.")
            return

        try:
            respond_url = hitl.build_respond_url(notification.request_id)
        except RuntimeError:
            # No base URL available (WEBSITE_HOSTNAME unset and no override). It is set
            # automatically on Azure Functions; locally add it to the host settings.
            # Notifying is best effort, the request is still reachable via the status
            # endpoint, so warn and continue rather than failing the workflow.
            logger.warning(
                "Cannot build a respond URL (WEBSITE_HOSTNAME unset). "
                "Skipping reviewer notification."
            )
            return

        recipient = require_env("ACS_RECIPIENT_EMAIL")
        subject = f"Terraform review needed: PR #{notification.pull_request_id}"
        html_body = self._build_html(notification, respond_url)

        await self._email_tools.send_email(recipient, subject, html_body)
        logger.info(
            "Sent approval request email to %s for PR #%s",
            recipient,
            notification.pull_request_id,
        )

    def _build_html(self, notification: ReviewerNotification, respond_url: str) -> str:
        """Build the approval email body with one-click approve and reject links.

        The reviewer POSTs to the respond URL, so the email gives the URL plus a ready
        to send JSON body for each decision. The base respond URL is the same for both,
        the body carries the approve/reject choice.
        """
        return f"""
            <p>A Terraform configuration is waiting for your review.</p>
            <p><strong>Pull request:</strong>
               <a href="{notification.pull_request_url}">#{notification.pull_request_id}</a></p>
            <p><strong>Summary:</strong> {notification.summary}</p>
            <p>Respond by POSTing to:</p>
            <pre>{respond_url}</pre>
            <p>Approve:</p>
            <pre>{{ "approved": true, "feedback": "Looks good, deploy it." }}</pre>
            <p>Reject and request changes:</p>
            <pre>{{ "approved": false, "feedback": "Describe the changes you want." }}</pre>
        """
