"""Live smoke tests against the real services (opt-in: ``EDI_MCP_LIVE=1 pytest -m live``).

DataONE tests run anonymously; PASTA tests also need ``EDI_API_KEY``.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import AsyncIterator

import pytest

from edi_mcp.config import Config
from edi_mcp.context import UpstreamStats
from edi_mcp.edi.auth import ApiKey
from edi_mcp.edi.backends import (
    DataOneBackend,
    PastaBackend,
    SearchHit,
    SearchQuery,
    resolve_package,
)
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


def _sort_key(hit: SearchHit, backend: PastaBackend | DataOneBackend) -> str | None:
    # PASTA sorts by publication date; DataONE by upload date (pubDate is unsortable there).
    value = hit.uploaded if isinstance(backend, DataOneBackend) else hit.pub_date
    return value[:4] if value else None


async def test_live_sort_orders_by_date(either: PastaBackend | DataOneBackend) -> None:
    newest = await either.search(SearchQuery(text="streamflow", sort="newest", limit=10))
    dates = [k for h in newest.hits if (k := _sort_key(h, either))]
    assert len(dates) >= 5 and dates == sorted(dates, reverse=True)
    oldest = await either.search(SearchQuery(text="streamflow", sort="oldest", limit=50))
    dated = [k for h in oldest.hits if (k := _sort_key(h, either))]
    assert dated == sorted(dated)


async def test_live_bbox_finds_the_region(either: PastaBackend | DataOneBackend) -> None:
    """Order is arbitrary without query text, so compare counts within one scope: Jornada's
    packages sit inside the Jornada box, and not inside its eastern-hemisphere mirror (which a
    sign or axis-order error would match instead)."""
    from edi_mcp.edi.backends import BoundingBox

    jornada = BoundingBox(-107, 32.4, -106.5, 32.8)
    mirrored = BoundingBox(106.5, 32.4, 107, 32.8)
    scope = "knb-lter-jrn"
    everything = (await either.search(SearchQuery(scope=scope, limit=1))).total or 0
    inside = (await either.search(SearchQuery(scope=scope, bbox=jornada, limit=1))).total or 0
    outside = (await either.search(SearchQuery(scope=scope, bbox=mirrored, limit=1))).total or 0
    assert everything > 50 and inside >= everything // 2, (everything, inside)
    assert outside <= everything // 20, (everything, outside)


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
    # New scopes still work (kind "unknown", passed through); a vanished one would make
    # the keyless snapshot answer wrong, so only that fails.
    assert known <= live, f"refresh scopes.json: gone from PASTA {sorted(known - live)}"
    if live - known:
        warnings.warn(f"scopes.json lacks new scopes {sorted(live - known)}", stacklevel=1)


@pytest.mark.parametrize(
    ("package", "scope_host"),
    [(HBR, "gmn.lternet.edu"), (PackageId("edi", 2081, 1), "gmn.edirepository.org")],
)
async def test_live_member_nodes_serve_data_without_a_key(
    client: EdiClient, package: PackageId, scope_host: str
) -> None:
    """edi_list_entities offers anonymousUrl on the member node (verified 2026-10-19; GMN
    ignores Range, so read only the first chunk)."""
    import httpx

    backend = DataOneBackend(client, Config.model_validate({}), UpstreamStats())
    entity = (await backend.list_entities(package))[0]
    url = backend.anonymous_data_url(package, entity.entity_id)
    assert scope_host in url
    async with httpx.AsyncClient(timeout=60) as http, http.stream("GET", url) as response:
        assert response.status_code == 200
        async for chunk in response.aiter_bytes():
            assert chunk
            break


# ---------------------------------------------------------------------- step 6


@pytest.fixture
def dataone(client: EdiClient) -> DataOneBackend:
    return DataOneBackend(client, Config.model_validate({}), UpstreamStats())


@pytest.mark.parametrize("package", [HBR, PackageId("edi", 2081, 1)])
async def test_live_quality_reports_are_anonymous_on_the_member_nodes(
    dataone: DataOneBackend, package: PackageId
) -> None:
    """edi_get_quality_report needs no key (D18, verified 2026-10-19)."""
    body = await dataone.read_report(package)
    assert b"qualityReport" in body[:2000] and package.package_id.encode() in body


async def test_live_entity_stream_closes_early(dataone: DataOneBackend) -> None:
    """Previews stop reading after the first chunk (GMN ignores Range)."""
    entity = "c4f72fa0cb155f1b61f1333bb67e3d00"
    async with dataone.stream_entity(HBR, entity) as stream:
        assert (stream.header("dataone-checksum") or "").upper().startswith("SHA-1,")
        async for chunk in stream.chunks():
            assert chunk.startswith(b"SRG_Num")
            break


async def test_live_citation_service(dataone: DataOneBackend) -> None:
    fields = await dataone.citation_fields(HBR)
    assert fields.doi == "doi:10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062"
    assert (await dataone.citation(HBR, "BIBTEX")).startswith("@misc{knb-lter-hbr.14.22,")


async def test_live_pasta_feeds(pasta: PastaBackend) -> None:
    """Changes, read counts and lineage parse; principals are never kept."""
    changes = await pasta.changes("2026-10-12", "2026-10-19", "edi")
    assert changes and all(c.package.scope == "edi" for c in changes)
    assert not any("EDI-" in repr(c) for c in changes)
    reads = await pasta.read_counts("edi", 2081, None)
    assert {r.resource_type for r in reads} >= {"dataPackage", "metadata", "data"}
    sources = await pasta.data_sources(HBR)
    assert sources and sources[0].title and "&#" not in sources[0].title
