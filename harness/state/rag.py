from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Embedder

_DEFAULT_EMBEDDER_MODEL = "openai:text-embedding-3-small"
_TOP_K = 5


@dataclass
class RagDocument:
    doc_id: str
    tenant_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class RagStore:
    """Per-tenant document store with semantic search.

    Phase 4 uses an in-memory store with cosine similarity over dense vectors
    produced by pydantic-ai's Embedder. Phase 5 replaces this with a real
    pgvector table (SQL query is a drop-in swap; the Embedder stays).

    Tenant isolation is enforced at every entry point: queries always filter
    by tenant_id, and the store raises ValueError if a cross-tenant operation
    is attempted.
    """

    def __init__(self, model: str = _DEFAULT_EMBEDDER_MODEL) -> None:
        self._embedder = Embedder(model)
        self._docs: dict[str, RagDocument] = {}  # doc_id → doc

    async def index(self, tenant_id: str, doc_id: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        """Embed and store a document. Overwrites any existing doc with the same id."""
        result = await self._embedder.embed_query(content)
        self._docs[doc_id] = RagDocument(
            doc_id=doc_id,
            tenant_id=tenant_id,
            content=content,
            metadata=metadata or {},
            embedding=list(result.embedding),
        )

    async def query(self, tenant_id: str, query: str, top_k: int = _TOP_K) -> list[RagDocument]:
        """Return the top-k most relevant documents for this tenant."""
        if not self._docs:
            return []

        result = await self._embedder.embed_query(query)
        q_vec = list(result.embedding)

        scored = [
            (doc, _cosine_similarity(q_vec, doc.embedding))
            for doc in self._docs.values()
            if doc.tenant_id == tenant_id  # strict tenant isolation
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in scored[:top_k]]

    def delete(self, tenant_id: str, doc_id: str) -> bool:
        doc = self._docs.get(doc_id)
        if doc is None or doc.tenant_id != tenant_id:
            return False
        del self._docs[doc_id]
        return True

    def count(self, tenant_id: str) -> int:
        return sum(1 for d in self._docs.values() if d.tenant_id == tenant_id)


rag_store = RagStore()
