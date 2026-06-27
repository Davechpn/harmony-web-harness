"""Phase 3 (Multi-Agent Threads) tests."""
from __future__ import annotations

import time

import pytest
from pydantic_ai.models.test import TestModel

from harness.core.models import (
    AuctionResearchOutput,
    Channel,
    EventPlannerOutput,
    HandoverRequest,
    InboundMessage,
    SenderType,
    TenantContext,
    TenantPolicy,
)
from harness.thread import invocation_gate
from harness.thread.floor import FloorState
from harness.thread.handover import handover_notification_text, make_handover_event
from harness.thread.locale import locale_instruction, resolve_reply_locale


# ── Floor control ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_floor_acquire_when_empty():
    floor = FloorState()
    ok = await floor.acquire("th1", "summariser")
    assert ok is True
    assert await floor.current_holder("th1") == "summariser"


@pytest.mark.asyncio
async def test_floor_acquire_blocked_by_other():
    floor = FloorState()
    await floor.acquire("th1", "summariser")
    blocked = await floor.acquire("th1", "event_planner")
    assert blocked is False
    assert await floor.current_holder("th1") == "summariser"


@pytest.mark.asyncio
async def test_floor_release():
    floor = FloorState()
    await floor.acquire("th1", "summariser")
    await floor.release("th1", "summariser")
    assert await floor.current_holder("th1") is None


@pytest.mark.asyncio
async def test_floor_transfer():
    floor = FloorState()
    await floor.acquire("th1", "event_planner")
    ok = await floor.transfer("th1", "event_planner", "auction_researcher")
    assert ok is True
    assert await floor.current_holder("th1") == "auction_researcher"


@pytest.mark.asyncio
async def test_floor_transfer_fails_if_wrong_holder():
    floor = FloorState()
    await floor.acquire("th1", "event_planner")
    ok = await floor.transfer("th1", "summariser", "auction_researcher")
    assert ok is False
    assert await floor.current_holder("th1") == "event_planner"


@pytest.mark.asyncio
async def test_floor_independent_per_thread():
    floor = FloorState()
    await floor.acquire("thread-A", "summariser")
    ok = await floor.acquire("thread-B", "event_planner")
    assert ok is True
    assert await floor.current_holder("thread-A") == "summariser"
    assert await floor.current_holder("thread-B") == "event_planner"


# ── Invocation gate ───────────────────────────────────────────────────────────

def _msg(text: str, mentions: list[str] | None = None, reply_to: str | None = None) -> InboundMessage:
    return InboundMessage(
        tenant_id="t1",
        channel=Channel.APP,
        thread_id="th1",
        message_id="m1",
        sender_type=SenderType.HUMAN,
        sender_id="u1",
        text=text,
        mentions=mentions or [],
        reply_to=reply_to,
        timestamp=time.time(),
    )


def _make_registry_stub():
    """Minimal registry stub with two agents."""
    from harness.core.registry import AgentSpec, AgentRegistry
    from unittest.mock import MagicMock

    registry = AgentRegistry.__new__(AgentRegistry)
    registry._specs = {}

    def make_spec(slug, trigger_phrases):
        spec = MagicMock(spec=AgentSpec)
        spec.slug = slug
        spec.trigger_phrases = trigger_phrases
        return spec

    registry._specs["summariser"] = make_spec("summariser", [])
    registry._specs["event_planner"] = make_spec("event_planner", ["plan", "event"])
    return registry


def test_gate_explicit_mention_fires():
    registry = _make_registry_stub()
    dec = invocation_gate.evaluate(
        _msg("@summariser please summarise", mentions=["@summariser"]),
        registry=registry,
        member_slugs=["summariser", "event_planner"],
        floor_holder=None,
    )
    assert dec.agent_slug == "summariser"
    assert dec.reason == "mention"


def test_gate_mention_of_non_member_ignored():
    registry = _make_registry_stub()
    dec = invocation_gate.evaluate(
        _msg("@event_planner help", mentions=["@event_planner"]),
        registry=registry,
        member_slugs=["summariser"],  # event_planner not a member here
        floor_holder=None,
    )
    assert dec.agent_slug is None
    assert dec.reason == "router"


def test_gate_trigger_phrase_required():
    registry = _make_registry_stub()
    dec = invocation_gate.evaluate(
        _msg("@event_planner lol", mentions=["@event_planner"]),
        registry=registry,
        member_slugs=["event_planner"],
        floor_holder=None,
    )
    # "lol" doesn't match any trigger phrase for event_planner
    assert dec.agent_slug is None
    assert dec.reason == "router"


def test_gate_trigger_phrase_match():
    registry = _make_registry_stub()
    dec = invocation_gate.evaluate(
        _msg("@event_planner help me plan the event", mentions=["@event_planner"]),
        registry=registry,
        member_slugs=["event_planner"],
        floor_holder=None,
    )
    assert dec.agent_slug == "event_planner"


def test_gate_reply_continuation_uses_floor_holder():
    registry = _make_registry_stub()
    dec = invocation_gate.evaluate(
        _msg("thanks", reply_to="prev-msg-id"),
        registry=registry,
        member_slugs=["summariser"],
        floor_holder="summariser",
    )
    assert dec.agent_slug == "summariser"
    assert dec.reason == "reply_continuation"


def test_gate_no_mention_no_floor_goes_to_router():
    registry = _make_registry_stub()
    dec = invocation_gate.evaluate(
        _msg("did anyone see the match last night?"),
        registry=registry,
        member_slugs=["summariser"],
        floor_holder=None,
    )
    assert dec.agent_slug is None
    assert dec.reason == "router"


# ── Handover ──────────────────────────────────────────────────────────────────

def test_handover_notification_text():
    req = HandoverRequest(
        to="auction_researcher",
        reason="need auction research",
        context_summary="50 chairs under R4k, deadline Friday",
        return_to="event_planner",
    )
    event = make_handover_event("event_planner", req)
    text = handover_notification_text(event)

    assert "@event_planner" in text
    assert "@auction_researcher" in text
    assert "50 chairs" in text
    assert "@event_planner" in text  # return_to mention


def test_handover_no_return_to():
    req = HandoverRequest(
        to="summariser",
        reason="summarise results",
        context_summary="research complete",
    )
    event = make_handover_event("auction_researcher", req)
    text = handover_notification_text(event)
    assert "@summariser" in text
    assert "return_to" not in text.lower() or "return" not in text.lower()


# ── Locale ────────────────────────────────────────────────────────────────────

def test_locale_sender_locale_used_if_allowed():
    assert resolve_reply_locale("fr") == "fr"


def test_locale_falls_back_to_tenant_default():
    assert resolve_reply_locale("xx-unknown", tenant_default="af") == "af"


def test_locale_instruction_empty_for_english():
    assert locale_instruction("en") == ""


def test_locale_instruction_non_english():
    instr = locale_instruction("fr")
    assert "fr" in instr
    assert len(instr) > 0


# ── New agent specs load correctly ────────────────────────────────────────────

from pathlib import Path

AGENTS_DIR = Path(__file__).parent.parent / "harness" / "agents"


@pytest.fixture
def full_registry():
    from harness.core.registry import AgentRegistry
    r = AgentRegistry()
    r.load_dir(AGENTS_DIR)
    return r


def test_event_planner_loads(full_registry):
    spec = full_registry.get("event_planner")
    assert spec is not None
    assert spec.slug == "event_planner"
    assert "plan" in spec.trigger_phrases


def test_auction_researcher_loads(full_registry):
    spec = full_registry.get("auction_researcher")
    assert spec is not None
    assert spec.slug == "auction_researcher"


def test_delegation_tool_registered(full_registry):
    """Event planner should have the delegate_to_researcher tool wired."""
    planner = full_registry.get("event_planner")
    assert planner is not None
    tool_names = list(planner.agent._function_toolset.tools)
    assert "delegate_to_researcher" in tool_names


# ── Two-agent handover flow (TestModel) ───────────────────────────────────────

def _ctx() -> TenantContext:
    return TenantContext(
        tenant_id="t1",
        locale="en",
        thread_id="th1",
        message_id="m1",
        sender_id="u1",
        policy=TenantPolicy(tenant_id="t1"),
    )


@pytest.mark.asyncio
async def test_event_planner_produces_handover(full_registry):
    planner = full_registry.get("event_planner")
    assert planner is not None

    expected = EventPlannerOutput(
        plan="Plan the event venue and source 50 chairs.",
        next_steps=["source chairs via auction"],
        handover=HandoverRequest(
            to="auction_researcher",
            reason="need auction research for chairs",
            context_summary="50 chairs under R4k, deadline Friday",
            return_to="event_planner",
        ),
    )

    # call_tools=[] prevents delegate_to_researcher from firing a real API call.
    with planner.agent.override(
        model=TestModel(call_tools=[], custom_output_args=expected.model_dump())
    ):
        result = await planner.agent.run(
            "Plan event: 50 chairs, R4k budget",
            deps=_ctx(),
        )

    assert isinstance(result.output, EventPlannerOutput)
    assert result.output.handover is not None
    assert result.output.handover.to == "auction_researcher"


@pytest.mark.asyncio
async def test_auction_researcher_output(full_registry):
    researcher = full_registry.get("auction_researcher")
    assert researcher is not None

    expected = AuctionResearchOutput(
        findings="Found 3 listings for folding chairs under R4k.",
        listings=[{"title": "50x Folding Chairs", "price": "R3800", "source": "BidOrBuy"}],
        sources=["bidorbuy.co.za"],
    )

    with researcher.agent.override(model=TestModel(custom_output_args=expected.model_dump())):
        result = await researcher.agent.run(
            "Find 50 folding chairs under R4k",
            deps=_ctx(),
        )

    assert isinstance(result.output, AuctionResearchOutput)
    assert "3 listings" in result.output.findings
