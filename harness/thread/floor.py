from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

_IDLE_TIMEOUT_SECONDS = 300  # floor auto-releases after 5 min of no activity


@dataclass
class _FloorEntry:
    holder: str
    acquired_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)


class FloorState:
    """In-memory floor lock per thread_id.

    One agent holds the floor at a time per thread. Others stay silent unless
    mentioned. Phase 5 replaces this with Redis so it works across workers.
    """

    def __init__(self) -> None:
        self._state: dict[str, _FloorEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, thread_id: str) -> asyncio.Lock:
        if thread_id not in self._locks:
            self._locks[thread_id] = asyncio.Lock()
        return self._locks[thread_id]

    def _is_expired(self, entry: _FloorEntry) -> bool:
        return time.time() - entry.last_activity > _IDLE_TIMEOUT_SECONDS

    async def current_holder(self, thread_id: str) -> str | None:
        async with self._lock(thread_id):
            entry = self._state.get(thread_id)
            if entry is None:
                return None
            if self._is_expired(entry):
                del self._state[thread_id]
                return None
            return entry.holder

    async def acquire(self, thread_id: str, agent_slug: str) -> bool:
        """Try to take the floor. Returns True if this agent now holds it."""
        async with self._lock(thread_id):
            existing = self._state.get(thread_id)
            if existing and not self._is_expired(existing) and existing.holder != agent_slug:
                return False
            self._state[thread_id] = _FloorEntry(holder=agent_slug)
            return True

    async def touch(self, thread_id: str, agent_slug: str) -> None:
        """Refresh the idle timer for the current floor holder."""
        async with self._lock(thread_id):
            entry = self._state.get(thread_id)
            if entry and entry.holder == agent_slug:
                entry.last_activity = time.time()

    async def release(self, thread_id: str, agent_slug: str) -> None:
        """Release the floor. No-op if this agent doesn't hold it."""
        async with self._lock(thread_id):
            entry = self._state.get(thread_id)
            if entry and entry.holder == agent_slug:
                del self._state[thread_id]

    async def transfer(self, thread_id: str, from_slug: str, to_slug: str) -> bool:
        """Transfer the floor from one agent to another atomically."""
        async with self._lock(thread_id):
            entry = self._state.get(thread_id)
            if entry is None or entry.holder != from_slug:
                return False
            self._state[thread_id] = _FloorEntry(holder=to_slug)
            return True


# Module-level singleton (safe for single-process dev; replaced by Redis in Phase 5).
floor_state = FloorState()
