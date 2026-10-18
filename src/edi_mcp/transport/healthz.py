"""``/healthz`` (liveness) and ``/readyz`` (readiness) for HTTP deployments."""

from __future__ import annotations

from typing import Any

from mcp.types import LATEST_PROTOCOL_VERSION
from starlette.requests import Request
from starlette.responses import JSONResponse

from edi_mcp import __version__


async def healthz(request: Request) -> JSONResponse:
    """Always 200 while the process serves; inspects nothing upstream."""
    del request
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "transport": "http",
        }
    )


async def readyz(request: Request) -> JSONResponse:
    """503 while startup work runs; 200 (``degraded`` flagged) afterwards. Never reveals the key."""
    server: Any = getattr(request.app.state, "edi_server", None)
    if server is None:  # pragma: no cover - misconfigured mount
        return JSONResponse({"status": "unknown"}, status_code=503)
    if server.readiness == "warming":
        return JSONResponse({"status": "warming"}, status_code=503)
    return JSONResponse(
        {
            "status": "ready",
            "degraded": server.readiness == "degraded",
            "keyConfigured": server.config.key_value() is not None,
        }
    )
