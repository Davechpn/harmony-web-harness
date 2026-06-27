from __future__ import annotations

import logfire


class VaultClient:
    """Per-tenant credential store.

    Credentials are isolated per tenant: an agent for tenant A can never see
    tenant B's secrets. Phase 4 uses an in-memory store; Phase 6 replaces it
    with encrypted Postgres + KMS.

    Usage at run time:
        credentials = await vault.get_credentials(tenant_id, "gmail")
        ctx = TenantContext(..., credentials={"gmail": credentials["token"]})
    """

    def __init__(self) -> None:
        # Keyed as _store[tenant_id][service] = {key: value}
        self._store: dict[str, dict[str, dict[str, str]]] = {}

    def set_credentials(self, tenant_id: str, service: str, creds: dict[str, str]) -> None:
        """Store credentials for a tenant/service pair (admin / test use)."""
        self._store.setdefault(tenant_id, {})[service] = creds

    async def get_credentials(self, tenant_id: str, service: str) -> dict[str, str]:
        """Return credentials for this tenant's service, or empty dict if not set."""
        creds = self._store.get(tenant_id, {}).get(service, {})
        if not creds:
            logfire.warn("no credentials found", tenant_id=tenant_id, service=service)
        return dict(creds)  # return a copy; never hand out the internal dict

    async def load_into_context(self, tenant_id: str, services: list[str]) -> dict[str, str]:
        """Load credentials for several services and merge into a flat dict.

        Keys are prefixed with the service name: {"gmail_token": "...", ...}
        """
        merged: dict[str, str] = {}
        for service in services:
            creds = await self.get_credentials(tenant_id, service)
            for k, v in creds.items():
                merged[f"{service}_{k}"] = v
        return merged


# Module-level singleton (safe for single-process dev; replace with a proper
# secrets manager — HashiCorp Vault, AWS Secrets Manager, etc. — in Phase 6).
vault = VaultClient()
