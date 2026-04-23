from typing import Any

from agent_framework import (
    Message,
)


def extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text

    messages = getattr(response, "messages", None)
    if isinstance(messages, list) and messages:
        last_message = messages[-1]
        if isinstance(last_message, Message):
            return last_message.text or ""

    return ""
