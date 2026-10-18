from __future__ import annotations

import json

from edi_mcp.server import EdiServer
from tests.helpers import TEST_KEY, call_ok


async def test_ping_without_key_reports_dataone(server: EdiServer) -> None:
    payload = await call_ok(server, "edi_ping")
    assert payload["pong"] == "ok"
    assert payload["protocolVersion"] == "2026-07-28"
    assert payload["keyConfigured"] is False and payload["keySource"] == "none"
    assert payload["backend"] == "dataone"
    assert payload["downloadsEnabled"] is True and payload["downloadDir"]
    assert payload["endpoints"]["pasta"] == "https://pasta.lternet.edu"
    assert any("2026-07-30" in note for note in payload["notes"])
    assert any("edi://guide/api-key" in step for step in payload["nextSteps"])
    assert payload["source"] == {
        "endpoints": [],
        "backend": "local",
        "cached": False,
        "derived": [],
    }


async def test_ping_with_key_reports_pasta_and_never_reveals_it(key_server: EdiServer) -> None:
    payload = await call_ok(key_server, "edi_ping")
    assert payload["keyConfigured"] is True and payload["keySource"] == "config"
    assert payload["backend"] == "pasta"
    assert payload["notes"] == []
    text = json.dumps(payload)
    assert TEST_KEY not in text and TEST_KEY[:8] not in text


async def test_ping_over_http_has_no_downloads(http_server: EdiServer) -> None:
    payload = await call_ok(http_server, "edi_ping")
    assert payload["transport"] == "http"
    assert payload["downloadsEnabled"] is False
    assert "downloadDir" not in payload


async def test_ping_takes_no_arguments(server: EdiServer) -> None:
    outcome = await server.call("edi_ping", {"check_api": True})
    assert outcome.is_error and outcome.payload["error"]["code"] == "invalid_argument"
