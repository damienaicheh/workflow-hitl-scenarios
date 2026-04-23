import json
from typing import Annotated

import aiohttp
from agent_framework import tool
from pydantic import Field


class TeamsTools:
    """Teams notifications via incoming webhook (Adaptive Cards)."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    @tool(
        name="send_teams_approval_card",
        description="Send an Adaptive Card to a Teams channel asking for human approval of a deployment plan.",
        approval_mode="never_require",
    )
    async def send_teams_approval_card(
        self,
        title: Annotated[
            str,
            Field(description="Card title, e.g. 'IaC Deployment Review'."),
        ],
        summary: Annotated[
            str,
            Field(description="Summary of what is being deployed (markdown supported)."),
        ],
        branch_name: Annotated[
            str,
            Field(description="Source branch name."),
        ],
        pr_url: Annotated[
            str,
            Field(description="URL of the Pull Request to review."),
        ],
    ) -> str:
        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Large",
                                "weight": "Bolder",
                                "text": title,
                            },
                            {
                                "type": "TextBlock",
                                "text": summary,
                                "wrap": True,
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Branch", "value": branch_name},
                                    {"title": "PR", "value": pr_url},
                                ],
                            },
                        ],
                        "actions": [
                            {
                                "type": "Action.OpenUrl",
                                "title": "Review PR",
                                "url": pr_url,
                            }
                        ],
                    },
                }
            ],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.webhook_url,
                json=card,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status not in (200, 202):
                    text = await response.text()
                    return f"Failed to send Teams card: HTTP {response.status} — {text}"

        return f"Adaptive Card sent to Teams: '{title}'."

    @tool(
        name="send_teams_status_card",
        description="Send a status update Adaptive Card to a Teams channel.",
        approval_mode="never_require",
    )
    async def send_teams_status_card(
        self,
        title: Annotated[
            str,
            Field(description="Card title."),
        ],
        status: Annotated[
            str,
            Field(description="Status, e.g. 'Approved', 'Deployed', 'Failed'."),
        ],
        details: Annotated[
            str,
            Field(description="Details text."),
        ],
    ) -> str:
        color_map = {
            "approved": "Good",
            "deployed": "Good",
            "failed": "Attention",
            "pending": "Warning",
        }
        style = color_map.get(status.lower(), "Default")

        card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Large",
                                "weight": "Bolder",
                                "text": title,
                            },
                            {
                                "type": "Container",
                                "style": style,
                                "items": [
                                    {
                                        "type": "TextBlock",
                                        "text": f"**Status:** {status}",
                                        "wrap": True,
                                    },
                                    {
                                        "type": "TextBlock",
                                        "text": details,
                                        "wrap": True,
                                    },
                                ],
                            },
                        ],
                    },
                }
            ],
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.webhook_url,
                json=card,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status not in (200, 202):
                    text = await response.text()
                    return f"Failed to send Teams card: HTTP {response.status} — {text}"

        return f"Status card sent to Teams: '{title}' — {status}."
