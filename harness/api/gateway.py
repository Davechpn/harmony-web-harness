from __future__ import annotations

import secrets
from typing import Any

import logfire
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from harness.api.deps import (
    get_normaliser,
    get_registry,
    get_telegram_adapter,
    resolve_credentials,
    resolve_policy,
    resolve_tenant_from_chat,
)
from harness.channels.app import CustomAppAdapter
from harness.channels.telegram import TelegramAdapter
from harness.core.models import (
    Channel,
    HandoverRequest,
    InboundMessage,
    OutboundMessage,
    TenantContext,
    TextBlock,
)
from harness.core.registry import AgentRegistry
from harness.core.settings import settings
from harness.gateway.normaliser import (
    DuplicateMessageError,
    InjectionDetectedError,
    Normaliser,
)
from harness.gateway.screen import screen
from harness.thread import invocation_gate, router as thread_router
from harness.thread.floor import floor_state
from harness.thread.handover import handover_notification_text, make_handover_event
from harness.thread.locale import locale_instruction, resolve_reply_locale

_router = APIRouter(prefix="/inbound", tags=["gateway"])


async def _dispatch(
    msg: InboundMessage,
    ctx: TenantContext,
    registry: AgentRegistry,
    deliver_fn: Any,
    channel: Channel,
) -> dict[str, Any]:
    """Full Phase 3 dispatch: gate → floor → run → handover."""

    member_slugs: list[str] = ctx.policy.thread_agents.get(ctx.thread_id, list(registry.all_slugs()))

    floor_holder = await floor_state.current_holder(ctx.thread_id)

    # ── Invocation gate ──────────────────────────────────────────────────────
    decision = invocation_gate.evaluate(
        msg,
        registry=registry,
        member_slugs=member_slugs,
        floor_holder=floor_holder,
    )

    agent_slug = decision.agent_slug
    if agent_slug is None and decision.reason == "router":
        # Cheap classification: should any member agent engage?
        agent_slug = await thread_router.classify(msg.text, member_slugs, registry)

    if agent_slug is None:
        logfire.info("no agent engaged", thread_id=ctx.thread_id, reason=decision.reason)
        return {"status": "silent", "reason": decision.reason}

    spec = registry.get(agent_slug)
    if spec is None:
        raise HTTPException(status_code=503, detail=f"agent {agent_slug!r} not loaded")

    # ── Acquire floor ────────────────────────────────────────────────────────
    acquired = await floor_state.acquire(ctx.thread_id, agent_slug)
    if not acquired:
        logfire.info("floor busy", thread_id=ctx.thread_id, holder=floor_holder)
        return {"status": "floor_busy", "holder": floor_holder}

    # ── Locale instruction ───────────────────────────────────────────────────
    reply_locale = resolve_reply_locale(msg.locale)
    extra_instruction = locale_instruction(reply_locale)

    # ── Run agent ────────────────────────────────────────────────────────────
    run_input = msg.text
    if extra_instruction:
        run_input = f"{extra_instruction}\n\n{msg.text}"

    try:
        with logfire.span("agent.run", agent=agent_slug, tenant_id=ctx.tenant_id, channel=channel):
            result = await spec.agent.run(run_input, deps=ctx, usage_limits=spec.usage_limits)
    finally:
        await floor_state.touch(ctx.thread_id, agent_slug)

    output = result.output

    # ── Check for handover ───────────────────────────────────────────────────
    handover: HandoverRequest | None = getattr(output, "handover", None)
    if handover:
        event = make_handover_event(agent_slug, handover)
        notification = handover_notification_text(event)

        notice_msg = OutboundMessage(
            tenant_id=ctx.tenant_id,
            channel=channel,
            thread_id=ctx.thread_id,
            blocks=[TextBlock(content=notification)],
            reply_to=msg.message_id,
            sender_agent_id="system",
        )
        await deliver_fn(notice_msg)
        await floor_state.transfer(ctx.thread_id, agent_slug, handover.to)
    else:
        await floor_state.release(ctx.thread_id, agent_slug)

    # ── Deliver reply ────────────────────────────────────────────────────────
    reply_text: str
    if hasattr(output, "plan"):
        reply_text = output.plan
    elif hasattr(output, "findings"):
        reply_text = output.findings
    elif hasattr(output, "summary"):
        reply_text = output.summary
    else:
        reply_text = str(output)

    outbound = OutboundMessage(
        tenant_id=ctx.tenant_id,
        channel=channel,
        thread_id=ctx.thread_id,
        blocks=[TextBlock(content=reply_text)],
        reply_to=msg.message_id,
        sender_agent_id=agent_slug,
    )
    await deliver_fn(outbound)
    return {"status": "ok", "agent": agent_slug, "handover": bool(handover)}


# ── Routes ───────────────────────────────────────────────────────────────────

router = _router  # exported name for app.include_router


@_router.post("/app")
async def inbound_app(
    request: Request,
    normaliser: Normaliser = Depends(get_normaliser),
    registry: AgentRegistry = Depends(get_registry),
) -> dict[str, Any]:
    raw = await request.json()

    try:
        msg, ctx = await normaliser.process(
            raw,
            resolve_policy=resolve_policy,
            resolve_credentials=resolve_credentials,
        )
    except DuplicateMessageError:
        return {"status": "duplicate", "skipped": True}
    except InjectionDetectedError as exc:
        raise HTTPException(status_code=400, detail=f"message rejected: {exc}") from exc

    adapter = CustomAppAdapter(
        nest_base_url=settings.nest_app_base_url,
        webhook_secret=settings.nest_app_webhook_secret,
    )
    return await _dispatch(msg, ctx, registry, adapter.deliver, Channel.APP)


@_router.post("/telegram")
async def inbound_telegram(
    request: Request,
    registry: AgentRegistry = Depends(get_registry),
    tg_adapter: TelegramAdapter = Depends(get_telegram_adapter),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if not secrets.compare_digest(
        x_telegram_bot_api_secret_token or "",
        settings.telegram_webhook_secret,
    ):
        raise HTTPException(status_code=403, detail="invalid telegram secret token")

    raw = await request.json()
    message = raw.get("message") or raw.get("edited_message") or {}
    chat_id = str(message.get("chat", {}).get("id", ""))
    if not chat_id:
        return {"status": "ignored", "reason": "no chat id"}

    tenant_id = await resolve_tenant_from_chat(chat_id)
    if tenant_id is None:
        return {"status": "ignored", "reason": "unknown chat"}

    msg = tg_adapter.parse(raw, tenant_id=tenant_id)
    policy = await resolve_policy(tenant_id)
    credentials = await resolve_credentials(tenant_id)
    ctx = TenantContext(
        tenant_id=tenant_id,
        locale=msg.locale,
        thread_id=msg.thread_id,
        message_id=msg.message_id,
        sender_id=msg.sender_id,
        credentials=credentials,
        policy=policy,
    )

    is_safe, reason = screen(msg)
    if not is_safe:
        logfire.warn("telegram injection screened", message_id=msg.message_id, reason=reason)
        return {"status": "rejected", "reason": "injection"}

    return await _dispatch(msg, ctx, registry, tg_adapter.deliver, Channel.TELEGRAM)
