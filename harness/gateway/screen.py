from __future__ import annotations

import re

from harness.core.models import InboundMessage

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous\s+)?(?:your\s+)?(instructions|rules|system prompt)", re.I),
    re.compile(r"you are now", re.I),
    re.compile(r"act as (an? |your )?(different|new|unrestricted)", re.I),
    re.compile(r"forward (everything|all messages|all emails) to", re.I),
    re.compile(r"<\s*script", re.I),
]


def screen(msg: InboundMessage) -> tuple[bool, str | None]:
    """Return (is_safe, reason). Drop or quarantine if not safe."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(msg.text):
            return False, f"injection pattern matched: {pattern.pattern!r}"
    return True, None
