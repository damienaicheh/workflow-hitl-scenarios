import os
from typing import Any

from azure.communication.email import EmailClient


class AcsEmailTools:
    """Send emails through Azure Communication Services.

    Uses the ACS connection string from `ACS_EMAIL_CONNECTION_STRING`.
    """

    def __init__(self) -> None:
        self._sender = os.environ["ACS_EMAIL_SENDER"]
        connection_string = os.environ["ACS_EMAIL_CONNECTION_STRING"]
        self._client = EmailClient.from_connection_string(connection_string)

    async def send_email(
        self,
        recipient: str,
        subject: str,
        html_body: str,
    ) -> dict[str, Any]:
        """Send an HTML email to a single recipient.

        Returns a dict with the ACS operation id and final status.
        """
        message = {
            "senderAddress": self._sender,
            "recipients": {"to": [{"address": recipient}]},
            "content": {"subject": subject, "html": html_body},
        }
        poller = self._client.begin_send(message)
        result = poller.result()
        return {
            "id": result["id"],
            "status": result["status"],
            "recipient": recipient,
            "subject": subject,
        }
