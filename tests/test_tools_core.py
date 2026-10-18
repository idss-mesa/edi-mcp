from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from edi_mcp.server import EdiServer
from tests.fixture_router import FixtureRouter
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


async def test_ping_rejects_unknown_arguments(server: EdiServer) -> None:
    outcome = await server.call("edi_ping", {"bogus": True})
    assert outcome.is_error and outcome.payload["error"]["code"] == "invalid_argument"


async def test_ping_makes_no_request_by_default(server: EdiServer, router: FixtureRouter) -> None:
    payload = await call_ok(server, "edi_ping")
    assert "api" not in payload and router.calls == []


async def test_ping_check_api_with_key_uses_a_token(
    key_server: EdiServer, router: FixtureRouter
) -> None:
    payload = await call_ok(key_server, "edi_ping", {"check_api": True})
    api = payload["api"]
    assert api["reachable"] is True and api["backend"] == "pasta"
    assert api["credential"] == "token" and api["endpoint"] == "GET pasta.lternet.edu/package/eml"
    assert payload["source"]["backend"] == "pasta"
    assert payload["source"]["endpoints"] == ["GET pasta.lternet.edu/package/eml"]
    assert TEST_KEY not in json.dumps(payload)
    assert len(router.auth_calls("/key")) == 1


async def test_ping_check_api_without_key_queries_dataone(
    server: EdiServer, router: FixtureRouter
) -> None:
    payload = await call_ok(server, "edi_ping", {"check_api": True})
    assert payload["api"]["reachable"] is True and payload["api"]["backend"] == "dataone"
    assert payload["api"]["credential"] == "none"
    assert {c.host for c in router.calls} == {"cn.dataone.org"}


async def test_ping_check_api_reports_a_bad_key(
    make_server: Callable[..., EdiServer], router: FixtureRouter
) -> None:
    server = make_server(key="definitely-wrong-key")
    payload = await call_ok(server, "edi_ping", {"check_api": True})
    assert payload["api"]["reachable"] is False
    assert payload["api"]["error"]["code"] == "upstream_forbidden"
    assert "definitely-wrong-key" not in json.dumps(payload)
    assert {c.host for c in router.calls} == {"auth.edirepository.org"}


async def test_ping_check_api_reports_an_outage(server: EdiServer, router: FixtureRouter) -> None:
    router.inject(httpx.ConnectError, times=3)
    payload = await call_ok(server, "edi_ping", {"check_api": True})
    assert payload["api"]["error"]["code"] == "upstream_unavailable"


async def test_ping_check_api_during_auth_outage_never_shows_the_key(
    key_server: EdiServer, router: FixtureRouter
) -> None:
    router.auth_mode = "down"
    outcome = await key_server.call("edi_ping", {"check_api": True})
    assert outcome.payload["api"]["credential"] == "key"
    assert TEST_KEY not in json.dumps(outcome.payload)
    assert TEST_KEY not in json.dumps(outcome.stats.endpoints)
