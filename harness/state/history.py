from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse

# Compress when stored messages exceed this fraction of the context window.
_COMPRESSION_THRESHOLD = 0.50

# Approximate token count for a message (coarse heuristic without a tokeniser).
_CHARS_PER_TOKEN = 4


def _approx_tokens(msg: ModelMessage) -> int:
    total = 0
    for part in msg.parts:
        content = getattr(part, "content", "") or ""
        if isinstance(content, str):
            total += len(content) // _CHARS_PER_TOKEN
        elif isinstance(content, list):
            for item in content:
                total += len(str(item)) // _CHARS_PER_TOKEN
    return max(total, 1)


def compress(
    messages: list[ModelMessage],
    context_window_tokens: int = 100_000,
) -> list[ModelMessage]:
    """Trim history so it stays under the compression threshold.

    Strategy (matches the Hermes heuristic):
    1. Keep all SystemPromptPart messages (they are instructions, not history).
    2. Keep the most recent turns until we're under the threshold.
    3. Insert a placeholder user turn describing what was dropped.

    This keeps recent context cheap and prevents long-lived threads from
    ballooning the prompt.
    """
    limit = int(context_window_tokens * _COMPRESSION_THRESHOLD)
    total = sum(_approx_tokens(m) for m in messages)
    if total <= limit:
        return messages

    # Work backwards from the most recent messages, accumulating tokens.
    kept: list[ModelMessage] = []
    accumulated = 0
    for msg in reversed(messages):
        cost = _approx_tokens(msg)
        if accumulated + cost > limit:
            break
        kept.append(msg)
        accumulated += cost

    kept.reverse()
    dropped = len(messages) - len(kept)

    # Prepend a summary stub so the model knows context was trimmed.
    summary_text = (
        f"[System: {dropped} earlier message(s) were compressed to stay within "
        f"context limits. Conversation continues below.]"
    )
    stub = ModelRequest.user_text_prompt(summary_text)
    return [stub, *kept]


@dataclass
class ThreadHistory:
    """In-memory per-thread message store.

    Phase 5 persists these to Postgres (keyed by tenant_id + thread_id).
    """

    tenant_id: str
    thread_id: str
    _messages: list[ModelMessage] = field(default_factory=list)

    def append(self, message: ModelMessage) -> None:
        self._messages.append(message)

    def extend(self, messages: list[ModelMessage]) -> None:
        self._messages.extend(messages)

    def get(self, context_window_tokens: int = 100_000) -> list[ModelMessage]:
        """Return the history, compressed if needed."""
        return compress(self._messages, context_window_tokens)

    def clear(self) -> None:
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)


class HistoryStore:
    """Registry of per-thread histories, scoped by tenant."""

    def __init__(self) -> None:
        # Keyed as _threads[(tenant_id, thread_id)]
        self._threads: dict[tuple[str, str], ThreadHistory] = {}

    def get_or_create(self, tenant_id: str, thread_id: str) -> ThreadHistory:
        key = (tenant_id, thread_id)
        if key not in self._threads:
            self._threads[key] = ThreadHistory(tenant_id=tenant_id, thread_id=thread_id)
        return self._threads[key]

    def clear(self, tenant_id: str, thread_id: str) -> None:
        self._threads.pop((tenant_id, thread_id), None)


history_store = HistoryStore()
