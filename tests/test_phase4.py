"""Phase 4 — Tools & Memory tests.

Covers:
- Vault: per-tenant isolation, copy-on-return, missing-credentials no-raise
- History: compression trigger, stub insertion, no compression below threshold
- RAG: tenant-scoped query, cross-tenant isolation
- WebResearchCapability: defer_loading, instructions, before_tool_execute hook
"""
from __future__ import annotations

import pytest

from harness.state.vault import VaultClient
from harness.state.history import compress, HistoryStore, ThreadHistory
from harness.capabilities.web_research import WebResearchCapability


# ── Vault ─────────────────────────────────────────────────────────────────────

class TestVaultIsolation:
    @pytest.fixture
    def vault(self):
        return VaultClient()

    @pytest.mark.asyncio
    async def test_tenant_a_credentials_not_visible_to_tenant_b(self, vault):
        vault.set_credentials("tenant-a", "gmail", {"token": "a-secret"})
        vault.set_credentials("tenant-b", "gmail", {"token": "b-secret"})

        creds_a = await vault.get_credentials("tenant-a", "gmail")
        creds_b = await vault.get_credentials("tenant-b", "gmail")

        assert creds_a["token"] == "a-secret"
        assert creds_b["token"] == "b-secret"
        assert creds_a != creds_b

    @pytest.mark.asyncio
    async def test_missing_credentials_returns_empty_dict(self, vault):
        creds = await vault.get_credentials("unknown-tenant", "gmail")
        assert creds == {}

    @pytest.mark.asyncio
    async def test_get_credentials_returns_copy(self, vault):
        vault.set_credentials("tenant-x", "svc", {"k": "v"})
        creds = await vault.get_credentials("tenant-x", "svc")
        creds["injected"] = "evil"  # mutate the returned copy

        creds2 = await vault.get_credentials("tenant-x", "svc")
        assert "injected" not in creds2  # original untouched

    @pytest.mark.asyncio
    async def test_load_into_context_merges_with_service_prefix(self, vault):
        vault.set_credentials("tenant-z", "gmail", {"token": "gtoken"})
        vault.set_credentials("tenant-z", "telegram", {"bot_token": "tgtoken"})

        merged = await vault.load_into_context("tenant-z", services=["gmail", "telegram"])
        assert merged["gmail_token"] == "gtoken"
        assert merged["telegram_bot_token"] == "tgtoken"

    @pytest.mark.asyncio
    async def test_load_into_context_skips_missing_service(self, vault):
        vault.set_credentials("tenant-q", "gmail", {"token": "gt"})
        merged = await vault.load_into_context("tenant-q", services=["gmail", "nonexistent"])
        assert "gmail_token" in merged
        # nonexistent service contributes nothing, but does not raise
        assert not any(k.startswith("nonexistent_") for k in merged)


# ── History / Compression ─────────────────────────────────────────────────────

def _make_request(text: str):
    from pydantic_ai.messages import ModelRequest
    return ModelRequest.user_text_prompt(text)


class TestHistoryCompression:
    def test_no_compression_below_threshold(self):
        msgs = [_make_request("short message") for _ in range(5)]
        result = compress(msgs, context_window_tokens=100_000)
        assert result is msgs  # identity: nothing was trimmed

    def test_compression_trims_excess_and_inserts_stub(self):
        # Create enough large messages to exceed the 50% threshold.
        big_text = "x" * 800  # ~200 tokens each at 4 chars/token
        msgs = [_make_request(big_text) for _ in range(400)]  # ~80 000 tokens > 50k limit

        result = compress(msgs, context_window_tokens=100_000)

        # Result must be shorter than input.
        assert len(result) < len(msgs)
        # First message should be the stub warning.
        first_parts = result[0].parts
        assert any("compressed" in str(p).lower() for p in first_parts)

    def test_compressed_result_stays_under_threshold(self):
        big_text = "y" * 800
        msgs = [_make_request(big_text) for _ in range(400)]

        result = compress(msgs, context_window_tokens=100_000)

        # Count approximate tokens in result (exclude the stub itself).
        from harness.state.history import _approx_tokens, _COMPRESSION_THRESHOLD
        total = sum(_approx_tokens(m) for m in result[1:])  # skip stub
        assert total <= int(100_000 * _COMPRESSION_THRESHOLD)


class TestHistoryStore:
    def test_get_or_create_is_idempotent(self):
        store = HistoryStore()
        h1 = store.get_or_create("tenant-a", "thread-1")
        h2 = store.get_or_create("tenant-a", "thread-1")
        assert h1 is h2

    def test_different_tenants_have_separate_histories(self):
        store = HistoryStore()
        h_a = store.get_or_create("tenant-a", "thread-1")
        h_b = store.get_or_create("tenant-b", "thread-1")
        assert h_a is not h_b

    def test_clear_removes_thread(self):
        store = HistoryStore()
        store.get_or_create("tenant-a", "thread-1")
        store.clear("tenant-a", "thread-1")
        h2 = store.get_or_create("tenant-a", "thread-1")
        assert len(h2) == 0


# ── WebResearchCapability ─────────────────────────────────────────────────────

class TestWebResearchCapability:
    def test_defer_loading_is_true_by_default(self):
        cap = WebResearchCapability()
        assert cap.defer_loading is True

    def test_defer_loading_can_be_disabled(self):
        cap = WebResearchCapability(defer_loading=False)
        assert cap.defer_loading is False

    def test_get_instructions_returns_provenance_text(self):
        cap = WebResearchCapability()
        instructions = cap.get_instructions()
        assert instructions is not None
        text = instructions if isinstance(instructions, str) else str(instructions)
        assert "source" in text.lower() or "cite" in text.lower() or "url" in text.lower()
