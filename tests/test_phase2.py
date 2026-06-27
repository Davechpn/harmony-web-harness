"""Phase 2 (Multi-Channel) tests."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from harness.channels.app import CustomAppAdapter
from harness.channels.telegram import TelegramAdapter
from harness.core.models import Channel, InboundMessage, SenderType


# ── Telegram adapter — parse ──────────────────────────────────────────────────

def _tg_update(
    update_id: int = 1,
    chat_id: int = -100123,
    user_id: int = 42,
    text: str = "Hello!",
    language_code: str = "en",
    reply_to_id: int | None = None,
) -> dict:
    message: dict = {
        "message_id": 9001,
        "from": {"id": user_id, "username": "alice", "language_code": language_code},
        "chat": {"id": chat_id, "type": "group"},
        "text": text,
        "entities": [],
        "date": 1_700_000_000,
    }
    if reply_to_id is not None:
        message["reply_to_message"] = {"message_id": reply_to_id}
    return {"update_id": update_id, "message": message}


def test_telegram_parse_basic():
    adapter = TelegramAdapter(bot_token="bot-token")
    msg = adapter.parse(_tg_update(), tenant_id="tenant-1")

    assert isinstance(msg, InboundMessage)
    assert msg.channel == Channel.TELEGRAM
    assert msg.tenant_id == "tenant-1"
    assert msg.thread_id == "-100123"
    assert msg.sender_id == "42"
    assert msg.text == "Hello!"
    assert msg.locale == "en"
    assert msg.sender_type == SenderType.HUMAN


def test_telegram_parse_locale_from_user():
    adapter = TelegramAdapter(bot_token="bot-token")
    msg = adapter.parse(_tg_update(language_code="fr"), tenant_id="tenant-1")
    assert msg.locale == "fr"


def test_telegram_parse_reply_to():
    adapter = TelegramAdapter(bot_token="bot-token")
    msg = adapter.parse(_tg_update(reply_to_id=8888), tenant_id="tenant-1")
    assert msg.reply_to == "8888"


def test_telegram_parse_no_reply():
    adapter = TelegramAdapter(bot_token="bot-token")
    msg = adapter.parse(_tg_update(), tenant_id="tenant-1")
    assert msg.reply_to is None


def test_telegram_parse_mentions():
    adapter = TelegramAdapter(bot_token="bot-token")
    raw = _tg_update(text="@SummariserBot please go")
    raw["message"]["entities"] = [{"type": "mention", "offset": 0, "length": 14}]
    msg = adapter.parse(raw, tenant_id="t1")
    assert "@SummariserBot" in msg.mentions


# ── Both adapters produce the same canonical shape ────────────────────────────

def _app_raw(message_id: str = "msg-1") -> dict:
    return {
        "tenantId": "tenant-abc",
        "threadId": "thread-1",
        "messageId": message_id,
        "senderId": "user-1",
        "senderType": "human",
        "text": "Summarise the last 10 messages.",
        "locale": "en",
        "timestamp": time.time(),
    }


def test_both_adapters_produce_same_inbound_shape():
    app_adapter = CustomAppAdapter(nest_base_url="http://localhost:3000", webhook_secret="s")
    tg_adapter = TelegramAdapter(bot_token="token")

    app_msg = app_adapter.parse(_app_raw())
    tg_msg = tg_adapter.parse(_tg_update(text="Summarise the last 10 messages."), tenant_id="tenant-abc")

    # Both must produce InboundMessage with all required fields populated.
    for msg in (app_msg, tg_msg):
        assert isinstance(msg, InboundMessage)
        assert msg.tenant_id
        assert msg.channel in Channel
        assert msg.thread_id
        assert msg.message_id
        assert msg.sender_id
        assert msg.locale
        assert msg.timestamp > 0


# ── Normaliser hardening — tenant_id validation ───────────────────────────────

@pytest.mark.asyncio
async def test_normaliser_rejects_invalid_tenant_id():
    from harness.gateway.normaliser import Normaliser

    adapter = CustomAppAdapter(nest_base_url="http://localhost:3000", webhook_secret="s")
    normaliser = Normaliser(adapter=adapter)

    raw = _app_raw()
    raw["tenantId"] = "bad tenant id with spaces!"

    async def stub_policy(tid: str):
        from harness.core.models import TenantPolicy
        return TenantPolicy(tenant_id=tid)

    with pytest.raises(ValueError, match="invalid or missing tenant_id"):
        await normaliser.process(raw, resolve_policy=stub_policy)


@pytest.mark.asyncio
async def test_normaliser_dedup_key_is_channel_scoped():
    """Same message_id on different channels must NOT be de-duplicated."""
    from harness.gateway.normaliser import Normaliser

    app_adapter = CustomAppAdapter(nest_base_url="http://localhost:3000", webhook_secret="s")
    normaliser = Normaliser(adapter=app_adapter)

    async def stub_policy(tid: str):
        from harness.core.models import TenantPolicy
        return TenantPolicy(tenant_id=tid)

    raw1 = _app_raw(message_id="shared-id")
    await normaliser.process(raw1, resolve_policy=stub_policy)

    # Second call with same message_id on same channel → duplicate
    raw2 = _app_raw(message_id="shared-id")
    from harness.gateway.normaliser import DuplicateMessageError
    with pytest.raises(DuplicateMessageError):
        await normaliser.process(raw2, resolve_policy=stub_policy)


# ── /inbound/telegram route — secret-token gate ───────────────────────────────

@pytest.mark.asyncio
async def test_telegram_route_rejects_bad_secret():
    """Requests without the correct Telegram webhook secret must get 403."""
    import os
    os.environ["TELEGRAM_BOT_TOKEN"] = "fake-token"
    os.environ["TELEGRAM_WEBHOOK_SECRET"] = "correct-secret"

    # Re-import app after env is set so settings picks them up.
    from importlib import reload
    import harness.core.settings as _s
    reload(_s)
    import harness.api.deps as _d
    _d.get_telegram_adapter.cache_clear()
    reload(_d)
    import harness.api.app as _app
    reload(_app)

    client = TestClient(_app.app)
    resp = client.post(
        "/inbound/telegram",
        json=_tg_update(),
        headers={"x-telegram-bot-api-secret-token": "wrong-secret"},
    )
    assert resp.status_code == 403
