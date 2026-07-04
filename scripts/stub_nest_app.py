"""Stub NestJS receiver for local testing.

Listens on the host/port set by NEST_APP_BASE_URL and accepts whatever the
harness's CustomAppAdapter.deliver() posts to /api/harness/outbound, printing
the message so you can see what the agent actually sent without running the
real NestJS app.
"""

from __future__ import annotations

import json

import uvicorn
from fastapi import FastAPI, Request

app = FastAPI()


@app.post("/api/harness/outbound")
async def outbound(request: Request) -> dict[str, str]:
    payload = await request.json()
    print("\n=== outbound message received ===")
    print(json.dumps(payload, indent=2))
    print("==================================\n")
    return {"status": "received"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=3000)
