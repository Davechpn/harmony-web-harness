from __future__ import annotations

import json

from pydantic_ai import ModelRequest
from pydantic_ai.direct import model_request
from pydantic_ai.messages import TextPart

from harness.core.registry import AgentRegistry

_ROUTER_MODEL = "openrouter:qwen/qwen3.5-9b"

_SYSTEM_PROMPT = """\
You are a lightweight message router for a multi-agent chat system.
Given a message and a list of available agents with their descriptions,
decide which single agent (if any) should respond.

Reply with ONLY a JSON object: {"agent": "<slug>"} or {"agent": null}.
Do not explain. Do not use markdown. Output raw JSON only.
"""


async def classify(
    message_text: str,
    member_slugs: list[str],
    registry: AgentRegistry,
) -> str | None:
    """Return the agent slug that should handle this message, or None.

    Uses a single cheap model call — no agent loop, no tools.
    """
    if not member_slugs:
        return None

    agents_desc = "\n".join(
        f"- {slug}" for slug in member_slugs if registry.get(slug) is not None
    )

    user_text = (
        f"Available agents:\n{agents_desc}\n\n"
        f"Message: {message_text}\n\n"
        "Which agent should respond? Reply with JSON only."
    )

    response = await model_request(
        _ROUTER_MODEL,
        [ModelRequest.user_text_prompt(user_text, instructions=_SYSTEM_PROMPT)],
    )

    raw_text = ""
    for part in response.parts:
        if isinstance(part, TextPart):
            raw_text += part.content

    try:
        data = json.loads(raw_text.strip())
        slug = data.get("agent")
        if slug and slug in member_slugs and registry.get(slug) is not None:
            return slug
    except (json.JSONDecodeError, AttributeError):
        pass

    return None
