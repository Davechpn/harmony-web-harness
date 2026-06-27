from __future__ import annotations

from dataclasses import dataclass, field

from harness.core.models import HandoverEvent, HandoverRequest


@dataclass
class PendingHandover:
    """Set by the handover tool during an agent run; checked by the gateway after."""
    request: HandoverRequest


def make_handover_event(from_agent: str, req: HandoverRequest) -> HandoverEvent:
    return HandoverEvent(
        from_agent=from_agent,
        to_agent=req.to,
        reason=req.reason,
        context_summary=req.context_summary,
        return_to=req.return_to,
    )


def handover_notification_text(event: HandoverEvent) -> str:
    """Human-readable thread event text posted when the floor transfers."""
    msg = (
        f"🔄 @{event.from_agent} handed off to @{event.to_agent} "
        f"— {event.reason}\n"
        f"Context: {event.context_summary}"
    )
    if event.return_to:
        msg += f"\n(Will return to @{event.return_to} when done.)"
    return msg
