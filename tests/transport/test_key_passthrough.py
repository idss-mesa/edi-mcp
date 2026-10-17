"""Per-request EDI keys over HTTP: the TLS gate, sharing policy and redaction (DESIGN.md D6)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from pydantic import SecretStr

from edi_mcp.config import Config
from edi_mcp.logging import setup_logging
from edi_mcp.server import EdiServer
from tests.helpers import TEST_KEY
from tests.helpers.asgi import AppHarness, rpc

HOST = "edi.example.test"


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    yield
    setup_logging("warning", "stdio")


def _server(
    make_server: Callable[..., EdiServer],
    config: Config,
    *,
    key: str | None = None,
    **server: Any,
) -> EdiServer:
    cfg = config.model_copy(deep=True)
    if key:
        cfg.edi.api_key = SecretStr(key)
    for name, value in server.items():
        setattr(cfg.server, name, value)
    return make_server(transport="http", config=cfg)


async def _ping(
    server: EdiServer,
    *,
    headers: dict[str, str] | None = None,
    base_url: str | None = None,
) -> tuple[str, dict[str, Any]]:
    harness = AppHarness(server, base_url=base_url) if base_url else AppHarness(server)
    async with harness as client:
        response, message = await rpc(
            client, "tools/call", {"name": "edi_ping", "arguments": {}}, headers=headers
        )
    return response.text, message["result"]["structuredContent"]


async def test_header_key_honoured_behind_tls(
    make_server: Callable[..., EdiServer], config: Config
) -> None:
    server = _server(make_server, config, public_base_url=f"https://{HOST}")
    text, payload = await _ping(server, headers={"X-EDI-Key": TEST_KEY}, base_url=f"http://{HOST}")
    assert payload["keyConfigured"] is True and payload["keySource"] == "request"
    assert payload["backend"] == "pasta"
    assert TEST_KEY not in text


async def test_header_key_ignored_without_tls(
    make_server: Callable[..., EdiServer], config: Config
) -> None:
    server = _server(make_server, config)
    _, payload = await _ping(server, headers={"X-EDI-Key": TEST_KEY})
    assert payload["keySource"] == "none" and payload["backend"] == "dataone"


async def test_insecure_override(make_server: Callable[..., EdiServer], config: Config) -> None:
    server = _server(make_server, config, allow_insecure_header_key=True)
    _, payload = await _ping(server, headers={"x-edi-key": TEST_KEY})
    assert payload["keySource"] == "request"


async def test_mcp_authorization_header_is_not_an_edi_key(
    make_server: Callable[..., EdiServer], config: Config
) -> None:
    server = _server(make_server, config, public_base_url=f"https://{HOST}")
    _, payload = await _ping(
        server, headers={"Authorization": f"Bearer {TEST_KEY}"}, base_url=f"http://{HOST}"
    )
    assert payload["keySource"] == "none"


async def test_config_key_not_shared_unless_opted_in(
    make_server: Callable[..., EdiServer], config: Config
) -> None:
    private = _server(make_server, config, key="operator-key-1234")
    _, payload = await _ping(private)
    assert payload["keySource"] == "none"
    shared = _server(make_server, config, key="operator-key-1234", share_config_key_over_http=True)
    _, payload = await _ping(shared)
    assert payload["keySource"] == "config"


async def test_key_never_logged(
    make_server: Callable[..., EdiServer], config: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_logging("debug", "http")
    server = _server(make_server, config, public_base_url=f"https://{HOST}")
    await _ping(server, headers={"X-EDI-Key": TEST_KEY}, base_url=f"http://{HOST}")
    captured = capsys.readouterr()
    assert "tool.call" in captured.err
    assert TEST_KEY not in captured.err and TEST_KEY not in captured.out
