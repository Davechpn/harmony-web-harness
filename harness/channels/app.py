from __future__ import annotations

import time
from typing import Any

import httpx

from harness.core.models import (
    Channel,
    InboundMessage,
    OutboundMessage,
    SenderType,
    TextBlock,
)


class CustomAppAdapter:
    """Adapter for the existing NestJS/React Native custom app channel."""

    def __init__(self, nest_base_url: str, webhook_secret: str) -> None:
        self._base_url = nest_base_url.rstrip("/")
        self._secret = webhook_secret

    def parse(self, raw: dict[str, Any]) -> InboundMessage:
        return InboundMessage(
            tenant_id=raw["tenantId"],
            channel=Channel.APP,
            thread_id=raw["threadId"],
            message_id=raw["messageId"],
            sender_type=SenderType.HUMAN if raw.get("senderType") == "human" else SenderType.AGENT,
            sender_id=raw["senderId"],
            text=raw.get("text", ""),
            mentions=raw.get("mentions", []),
            reply_to=raw.get("replyTo"),
            locale=raw.get("locale", "en"),
            timestamp=raw.get("timestamp", time.time()),
        )

    async def deliver(self, msg: OutboundMessage) -> None:
        text_parts = [b.content for b in msg.blocks if isinstance(b, TextBlock)]
        payload = {
            "tenantId": msg.tenant_id,
            "threadId": msg.thread_id,
            "replyTo": msg.reply_to,
            "senderAgentId": msg.sender_agent_id,
            "text": "\n".join(text_parts),
            "blocks": [b.model_dump() for b in msg.blocks],
        }
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self._base_url}/api/harness/outbound",
                json=payload,
                headers={"x-harness-secret": self._secret},
                timeout=10,
            )
