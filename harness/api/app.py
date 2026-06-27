from __future__ import annotations

import logfire
from fastapi import FastAPI

from harness.api.gateway import router as gateway_router
from harness.core.settings import settings

app = FastAPI(title="Harmony Web Harness", version="0.1.0")

if settings.logfire_token:
    logfire.configure(token=settings.logfire_token)
    logfire.instrument_fastapi(app)
    logfire.instrument_pydantic_ai()

app.include_router(gateway_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
