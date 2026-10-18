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


# Semantic checks the replayed fixtures cannot make: a filter Solr silently ignores
# (as PASTA ignores ``sort=pubdate desc``) would still replay "successfully".


@pytest.fixture(params=["pasta", "dataone"])
def either(request: pytest.FixtureRequest, client: EdiClient) -> PastaBackend | DataOneBackend:
    cfg = Config.model_validate({})
    if request.param == "dataone":
        return DataOneBackend(client, cfg, UpstreamStats())
    key = os.environ.get("EDI_API_KEY", "").strip()
    if not key:
        pytest.skip("EDI_API_KEY is not set")
    return PastaBackend(client, cfg, UpstreamStats(), ApiKey(key, "config"))


async def test_live_sort_orders_by_publication_date(either: PastaBackend | DataOneBackend) -> None:
    newest = await either.search(SearchQuery(text="streamflow", sort="newest", limit=10))
    dates = [h.pub_date[:4] for h in newest.hits if h.pub_date]
    assert len(dates) >= 5 and dates == sorted(dates, reverse=True)
    oldest = await either.search(SearchQuery(text="streamflow", sort="oldest", limit=50))
    dated = [h.pub_date[:4] for h in oldest.hits if h.pub_date]
    assert dated == sorted(dated)


async def test_live_bbox_finds_the_region(either: PastaBackend | DataOneBackend) -> None:
    from edi_mcp.edi.backends import BoundingBox

    jornada = BoundingBox(-107, 32.4, -106.5, 32.8)
    page = await either.search(SearchQuery(bbox=jornada, limit=10))
    scopes = [h.package.scope for h in page.hits]
    assert scopes.count("knb-lter-jrn") >= 5, scopes
    # The same box mirrored to the eastern hemisphere (a sign error) holds no Jornada data.
    mirrored = await either.search(SearchQuery(bbox=BoundingBox(106.5, 32.4, 107, 32.8)))
    assert not any(h.package.scope == "knb-lter-jrn" for h in mirrored.hits)


async def test_live_author_ignores_case(either: PastaBackend | DataOneBackend) -> None:
    lower = await either.search(SearchQuery(author="likens", limit=5))
    upper = await either.search(SearchQuery(author="LIKENS", limit=5))
    assert lower.total and lower.total == upper.total
    assert {h.package.series for h in lower.hits} == {h.package.series for h in upper.hits}


async def test_live_temporal_overlap(either: PastaBackend | DataOneBackend) -> None:
    page = await either.search(SearchQuery(start_year=1960, end_year=1965, limit=10))
    assert page.hits
    for hit in page.hits:
        assert (hit.begin_date or "0000")[:4] <= "1965" and (hit.end_date or "9999")[:4] >= "1960"


async def test_live_scope_snapshot_is_current(pasta: PastaBackend) -> None:
    from edi_mcp.edi.scopes import load_scopes

    live = set(await pasta.list_scopes())
    known = {r.scope for r in load_scopes().records}
    assert live == known, f"refresh scopes.json: new {live - known}, gone {known - live}"
