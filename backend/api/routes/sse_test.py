"""SSE smoke-test endpoint.

Verifies that Server-Sent Events make it through nginx-proxy-manager + Cloudflare to
the browser. sse-starlette adds the necessary `Cache-Control: no-cache` and
`X-Accel-Buffering: no` response headers automatically; if the stream is still buffered,
it's a proxy/CDN config issue, not the app.

Use:  curl -N https://wc26.tinjak.com/sse/tick
      → should emit one event every 2s without buffering
"""
import asyncio
import time

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter()


@router.get("/tick")
async def tick(request: Request):
    """Emit a single tick every 2 seconds for 30 ticks (1 minute), then close.
    Verifies the proxy pipeline without holding a connection forever."""
    async def generator():
        for i in range(30):
            if await request.is_disconnected():
                return
            yield {"event": "tick", "data": {"i": i, "ts": time.time()}}
            await asyncio.sleep(2.0)

    # ping=15: send a keep-alive comment every 15s of silence (defeats proxy idle-timeouts).
    return EventSourceResponse(generator(), ping=15)
