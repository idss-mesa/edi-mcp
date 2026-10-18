"""Shared fixtures: config, server factory, secret/warning isolation.

Unit tests never touch the network. The hermetic upstream router arrives with
the HTTP client (build-order step 3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from edi_mcp.config import Config
from edi_mcp.edi.auth import _reset_warning_for_tests
from edi_mcp.logging import forget_secrets
from edi_mcp.server import EdiServer, create_server
from tests.helpers import TEST_KEY


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    yield
    forget_secrets()
    _reset_warning_for_tests()


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config.model_validate({"downloads": {"directory": str(tmp_path / "downloads")}})


@pytest.fixture
async def make_server(config: Config) -> AsyncIterator[Callable[..., EdiServer]]:
    servers: list[EdiServer] = []

    def _make(
        *,
        transport: str = "stdio",
        key: str | None = None,
        config: Config | None = None,
        **_: Any,
    ) -> EdiServer:
        cfg = (config or _base).model_copy(deep=True)
        if key:
            cfg.edi.api_key = SecretStr(key)
        server = create_server(cfg, transport=transport)  # type: ignore[arg-type]
        servers.append(server)
        return server

    _base = config
    yield _make
    for server in servers:
        await server.aclose()


@pytest.fixture
async def server(make_server: Callable[..., EdiServer]) -> EdiServer:
    return make_server()


@pytest.fixture
async def key_server(make_server: Callable[..., EdiServer]) -> EdiServer:
    return make_server(key=TEST_KEY)


@pytest.fixture
async def http_server(make_server: Callable[..., EdiServer]) -> EdiServer:
    return make_server(transport="http")
