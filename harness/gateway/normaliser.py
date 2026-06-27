from __future__ import annotations

import hashlib
import re
import time
from typing import Any

import logfire

from harness.channels.base import ChannelAdapter
from harness.core.models import InboundMessage, TenantContext, TenantPolicy
from harness.gateway.screen import screen

_TENANT_ID_RE = re.compile(r"^[\w\-]{1,128}$")


class DuplicateMessageError(Exception):
    pass


class InjectionDetectedError(Exception):
    pass


class Normaliser:
    """Front door: parses, deduplicates, screens, and emits (InboundMessage, TenantContext).

    Each channel (app, Telegram, …) constructs its own Normaliser with the
    matching adapter. Dedup is in-process with a TTL; replace with Redis in
    Phase 5 when workers run on multiple hosts.
    """

    def __init__(self, adapter: ChannelAdapter, seen_ttl_seconds: int = 300) -> None:
        self._adapter = adapter
        self._seen: dict[str, float] = {}
        self._seen_ttl = seen_ttl_seconds

    def _dedup_key(self, msg: InboundMessage) -> str:
        # Include tenant_id to prevent cross-tenant collisions on the same message_id.
        return hashlib.sha256(
            f"{msg.tenant_id}:{msg.channel}:{msg.message_id}".encode()
        ).hexdigest()

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [k for k, t in self._seen.items() if now - t > self._seen_ttl]
        for k in expired:
            del self._seen[k]

    async def process(
        self,
        raw: dict[str, Any],
        *,
        resolve_policy: Any,
        resolve_credentials: Any | None = None,
    ) -> tuple[InboundMessage, TenantContext]:
        msg = self._adapter.parse(raw)

        if not msg.tenant_id or not _TENANT_ID_RE.match(msg.tenant_id):
            raise ValueError(f"invalid or missing tenant_id: {msg.tenant_id!r}")

        if not msg.thread_id:
            raise ValueError("inbound message missing thread_id")

        self._evict_expired()
        key = self._dedup_key(msg)
        if key in self._seen:
            raise DuplicateMessageError(msg.message_id)
        self._seen[key] = time.time()

        is_safe, reason = screen(msg)
        if not is_safe:
            logfire.warn(
                "injection screened",
                message_id=msg.message_id,
                channel=msg.channel,
                reason=reason,
            )
            raise InjectionDetectedError(reason)

        policy: TenantPolicy = await resolve_policy(msg.tenant_id)
        credentials: dict[str, str] = (
            await resolve_credentials(msg.tenant_id) if resolve_credentials else {}
        )

        ctx = TenantContext(
            tenant_id=msg.tenant_id,
            locale=msg.locale,
            thread_id=msg.thread_id,
            message_id=msg.message_id,
            sender_id=msg.sender_id,
            credentials=credentials,
            policy=policy,
        )

        logfire.info(
            "message normalised",
            tenant_id=msg.tenant_id,
            channel=msg.channel,
            thread_id=msg.thread_id,
            message_id=msg.message_id,
        )
        return msg, ctx
