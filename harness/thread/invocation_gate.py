from __future__ import annotations

import re
from dataclasses import dataclass

from harness.core.models import InboundMessage
from harness.core.registry import AgentRegistry


@dataclass
class InvocationDecision:
    agent_slug: str | None
    reason: str  # "mention", "reply_continuation", "floor_continuation", "router", "none"


def _normalise_mention(mention: str) -> str:
    """Strip leading @ and lowercase for comparison."""
    return mention.lstrip("@").lower()


def _strip_mentions(text: str) -> str:
    """Remove @mention tokens so they don't accidentally match trigger phrases."""
    return re.sub(r"@\S+", "", text).strip()


def _matches_trigger_phrases(text: str, phrases: list[str]) -> bool:
    """Empty phrases list means any message fires. Otherwise at least one must match.

    Mentions are stripped first so that '@event_planner' doesn't accidentally
    match the 'plan' or 'event' trigger phrases.
    """
    if not phrases:
        return True
    body = _strip_mentions(text).lower()
    return any(re.search(re.escape(p.lower()), body) for p in phrases)


def evaluate(
    msg: InboundMessage,
    *,
    registry: AgentRegistry,
    member_slugs: list[str],
    floor_holder: str | None,
) -> InvocationDecision:
    """Three-condition invocation gate (cheap, no model call).

    Returns the agent that should respond, or None (drop silently).

    Conditions for a direct activation (all required):
      1. Message @mentions an agent that is a member of this thread.
      2. Message matches that agent's configured trigger phrases.
      3. The mentioned agent exists in the registry.

    Fallback chain:
      - Message is a reply to a floor-holding agent → continue with that agent.
      - A floor holder is active → continue (humans chatting only gets through router).
      - Otherwise → caller should invoke the router.
    """
    member_set = set(member_slugs)

    # ── Condition: explicit @mention of a member agent ──────────────────────
    for raw_mention in msg.mentions:
        slug = _normalise_mention(raw_mention)
        if slug not in member_set:
            continue  # @mention of a non-member — ignore silently
        spec = registry.get(slug)
        if spec is None:
            continue
        if _matches_trigger_phrases(msg.text, spec.trigger_phrases):
            return InvocationDecision(agent_slug=slug, reason="mention")

    # ── Condition: reply to a message from the floor holder ─────────────────
    if msg.reply_to and floor_holder and floor_holder in member_set:
        return InvocationDecision(agent_slug=floor_holder, reason="reply_continuation")

    # ── Floor holder is active (no mention, not a reply) ────────────────────
    # Humans are chatting; let the router decide if any agent should engage.
    return InvocationDecision(agent_slug=None, reason="router")
