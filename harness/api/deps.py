"""Shared FastAPI dependency providers."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from harness.channels.app import CustomAppAdapter
from harness.channels.telegram import TelegramAdapter
from harness.core.models import TenantPolicy
from harness.core.registry import AgentRegistry
from harness.core.settings import settings
from harness.gateway.normaliser import Normaliser
from harness.state.vault import vault


@lru_cache
def get_registry() -> AgentRegistry:
    registry = AgentRegistry()
    agents_dir = Path(__file__).parent.parent / "agents"
    registry.load_dir(agents_dir)
    return registry


@lru_cache
def get_normaliser() -> Normaliser:
    adapter = CustomAppAdapter(
        nest_base_url=settings.nest_app_base_url,
        webhook_secret=settings.nest_app_webhook_secret,
    )
    return Normaliser(adapter=adapter)


@lru_cache
def get_telegram_adapter() -> TelegramAdapter:
    return TelegramAdapter(bot_token=settings.telegram_bot_token)


async def resolve_policy(tenant_id: str) -> TenantPolicy:
    """Stub: load tenant policy from DB. Replace with real DB query in Phase 6."""
    return TenantPolicy(tenant_id=tenant_id)


async def resolve_credentials(tenant_id: str) -> dict[str, str]:
    """Load all registered credentials for a tenant from the vault.

    Phase 4: in-memory vault stub. Phase 6 replaces with encrypted Postgres + KMS.
    Credentials are injected into TenantContext per-run and never stored in any agent.
    """
    # Load all services that might be registered for this tenant.
    # Phase 6 will query the vault's service registry for the tenant's configured services.
    return await vault.load_into_context(tenant_id, services=["gmail", "telegram", "web"])


async def resolve_tenant_from_chat(chat_id: str) -> str | None:
    """Stub: map Telegram chat_id → tenant_id via NestJS. Replace in Phase 6.

    Returns None if the chat is unknown (drop the message silently).
    """
    # Placeholder: treat chat_id as tenant_id for local dev.
    return chat_id if chat_id else None
