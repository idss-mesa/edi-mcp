from __future__ import annotations

from collections.abc import Callable

from edi_mcp.server import EdiServer
from tests.helpers import TEST_KEY
from tests.helpers.asgi import AppHarness


async def test_healthz_and_readyz_are_public_and_secret_free(
    make_server: Callable[..., EdiServer],
) -> None:
    server = make_server(transport="http", key=TEST_KEY)
    async with AppHarness(server) as client:
        response = await client.get("/healthz")
        ready = await client.get("/readyz")
    body = response.json()
    assert response.status_code == 200
    assert (
        body["status"] == "ok"
        and body["protocolVersion"] == "2026-07-28"
        and body["transport"] == "http"
    )
    assert TEST_KEY not in response.text and TEST_KEY not in ready.text
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "degraded": False, "keyConfigured": True}


async def test_readyz_warming_and_degraded(http_server: EdiServer) -> None:
    async with AppHarness(http_server) as client:
        http_server.readiness = "warming"
        warming = await client.get("/readyz")
        http_server.readiness = "degraded"
        degraded = await client.get("/readyz")
    assert warming.status_code == 503 and warming.json() == {"status": "warming"}
    assert degraded.status_code == 200 and degraded.json()["degraded"] is True
    assert degraded.json()["keyConfigured"] is False
