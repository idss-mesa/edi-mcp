"""Live smoke tests against the real services (opt-in: ``EDI_MCP_LIVE=1 pytest -m live``).

DataONE tests run anonymously; PASTA tests also need ``EDI_API_KEY``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

from edi_mcp.config import Config
from edi_mcp.context import UpstreamStats
from edi_mcp.edi.auth import ApiKey
from edi_mcp.edi.backends import DataOneBackend, PastaBackend, SearchQuery, resolve_package
from edi_mcp.edi.client import EdiClient
from edi_mcp.edi.pid import PackageId

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("EDI_MCP_LIVE") != "1", reason="set EDI_MCP_LIVE=1"),
]
HBR = PackageId("knb-lter-hbr", 14, 22)


@pytest.fixture
async def client() -> AsyncIterator[EdiClient]:
    cfg = Config.model_validate({})
    c = EdiClient(cfg.edi, cfg.cache)
    yield c
    await c.aclose()


@pytest.fixture
def pasta(client: EdiClient) -> PastaBackend:
    key = os.environ.get("EDI_API_KEY", "").strip()
    if not key:
        pytest.skip("EDI_API_KEY is not set")
    return PastaBackend(client, Config.model_validate({}), UpstreamStats(), ApiKey(key, "config"))


async def test_live_dataone(client: EdiClient) -> None:
    backend = DataOneBackend(client, Config.model_validate({}), UpstreamStats())
    page = await backend.search(SearchQuery(text="streamflow", limit=3))
    assert page.hits
    assert b"<dataset" in await backend.read_eml(HBR)
    assert any(e.name == "thiessen_weights" for e in await backend.list_entities(HBR))
    assert (
        await resolve_package(backend, "doi:10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062")
    ).package == HBR


async def test_live_pasta(pasta: PastaBackend) -> None:
    assert "knb-lter-hbr" in await pasta.list_scopes()
    assert pasta.stats.credential == "token"
    revisions = await pasta.list_revisions("knb-lter-hbr", 14)
    assert 22 in revisions
    assert (await pasta.search(SearchQuery(text="streamflow", limit=3))).hits
    assert await pasta.package_doi(HBR) == "doi:10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062"
