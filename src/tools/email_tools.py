from typing import Annotated

from agent_framework import tool
from azure.communication.email import EmailClient
from pydantic import Field


class EmailTools:
    """Send email notifications via Azure Communication Services."""

    def __init__(self, connection_string: str, sender_email: str):
        self.client = EmailClient.from_connection_string(connection_string)
        self.sender_email = sender_email

    @tool(
        name="send_deployment_email",
        description="Send a deployment status email via Azure Communication Services.",
        approval_mode="never_require",
    )
    async def send_deployment_email(
        self,
        recipient: Annotated[
            str,
            Field(description="Recipient email address."),
        ],
        subject: Annotated[
            str,
            Field(description="Email subject."),
        ],
        body_html: Annotated[
            str,
            Field(description="Email body in HTML."),
        ],
    ) -> str:
        message = {
            "senderAddress": self.sender_email,
            "recipients": {
                "to": [{"address": recipient}],
            },
            "content": {
                "subject": subject,
                "html": body_html,
            },
        }
        try:
            poller = self.client.begin_send(message)
            result = poller.result()
        except Exception as exc:
            return f"Failed to send email: {exc}"

        msg_id = result.get("id", "unknown") if isinstance(result, dict) else "unknown"
        status = result.get("status", "unknown") if isinstance(result, dict) else "unknown"
        return f"Email sent (id={msg_id}, status={status})."
