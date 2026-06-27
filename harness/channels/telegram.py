from __future__ import annotations

import json
from typing import Any

import httpx

from harness.core.models import (
    Channel,
    InboundMessage,
    OutboundMessage,
    SenderType,
    TextBlock,
)


class TelegramAdapter:
    """Adapter for the Telegram Bot API channel.

    Parses an inbound Update object and delivers OutboundMessage via sendMessage.
    The tenant_id is injected by the caller (resolved from chat_id by the route
    handler, which consults the NestJS tenant authority).
    """

    TELEGRAM_API = "https://api.telegram.org"

    def __init__(self, bot_token: str) -> None:
        self._token = bot_token

    def _api_url(self, method: str) -> str:
        return f"{self.TELEGRAM_API}/bot{self._token}/{method}"

    def parse(self, raw: dict[str, Any], *, tenant_id: str) -> InboundMessage:
        """Parse a Telegram Update dict into a canonical InboundMessage.

        tenant_id is passed in rather than derived from the payload because
        Telegram payloads carry no tenant concept — the mapping lives in NestJS.
        """
        message = raw.get("message") or raw.get("edited_message") or {}
        from_user = message.get("from", {})
        chat = message.get("chat", {})
        entities = message.get("entities") or []

        mentions = [
            message["text"][e["offset"]: e["offset"] + e["length"]]
            for e in entities
            if e.get("type") == "mention"
        ]

        return InboundMessage(
            tenant_id=tenant_id,
            channel=Channel.TELEGRAM,
            thread_id=str(chat.get("id", "")),
            message_id=str(raw.get("update_id", "")),
            sender_type=SenderType.HUMAN,
            sender_id=str(from_user.get("id", "")),
            text=message.get("text", ""),
            mentions=mentions,
            reply_to=str(message["reply_to_message"]["message_id"])
            if message.get("reply_to_message")
            else None,
            locale=from_user.get("language_code", "en"),
            timestamp=float(message.get("date", 0)),
        )

    async def deliver(self, msg: OutboundMessage) -> None:
        text_parts = [b.content for b in msg.blocks if isinstance(b, TextBlock)]
        text = "\n".join(text_parts)

        payload: dict[str, Any] = {
            "chat_id": msg.thread_id,
            "text": text,
            "parse_mode": "MarkdownV2",
        }
        if msg.reply_to:
            payload["reply_parameters"] = {"message_id": int(msg.reply_to)}

        async with httpx.AsyncClient() as client:
            resp = await client.post(self._api_url("sendMessage"), json=payload, timeout=10)
            resp.raise_for_status()
