"""PASTA and DataONE backends against recorded fixtures (both routes, same contract)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import pytest

from edi_mcp.config import Config
from edi_mcp.context import UpstreamStats
from edi_mcp.edi.auth import ApiKey
from edi_mcp.edi.backends import (
    DataOneBackend,
    PastaBackend,
    SearchQuery,
    backend_for,
    resolve_package,
)
from edi_mcp.edi.backends.dataone import solr_escape
from edi_mcp.edi.client import EdiClient
from edi_mcp.edi.pid import Doi, PackageId
from edi_mcp.errors import ToolError
from edi_mcp.server import EdiServer
from tests.fixture_router import FixtureRouter, Reply
from tests.helpers import TEST_KEY

HBR = PackageId("knb-lter-hbr", 14, 22)
EDI = PackageId("edi", 2081, 1)
HBR_DOI = Doi("2017345f0977c0f7c46e1ad90ce1b062")
OLD_DOI = Doi("cb5f623deb94bdefc7502655b03f6645")
THIESSEN = "c4f72fa0cb155f1b61f1333bb67e3d00"


@pytest.fixture
async def client(router: FixtureRouter) -> AsyncIterator[EdiClient]:
    cfg = Config.model_validate({})
    c = EdiClient(cfg.edi, cfg.cache, http_transport=router.transport)
    yield c
    await c.aclose()


@pytest.fixture
def pasta(client: EdiClient) -> PastaBackend:
    cfg = Config.model_validate({})
    stats = UpstreamStats()
    backend = PastaBackend(client, cfg, stats, ApiKey(TEST_KEY, "config"))
    backend.set_fallback(DataOneBackend(client, cfg, stats))
    return backend


@pytest.fixture
def dataone(client: EdiClient) -> DataOneBackend:
    return DataOneBackend(client, Config.model_validate({}), UpstreamStats())


Factory = Callable[[], PastaBackend | DataOneBackend]


# ---------------------------------------------------------------------- PASTA


async def test_pasta_listings(pasta: PastaBackend) -> None:
    scopes = await pasta.list_scopes()
    assert {"edi", "knb-lter-hbr", "knb-lter-jrn"} <= set(scopes)
    identifiers = await pasta.list_identifiers("knb-lter-hbr")
    assert 14 in identifiers and identifiers == sorted(identifiers)
    assert await pasta.list_revisions("knb-lter-hbr", 14) == list(range(6, 23))
    assert await pasta.list_revisions("knb-lter-hbr", 999999) == []
    assert pasta.stats.backend == "pasta" and pasta.stats.credential == "token"


async def test_pasta_package_facts(pasta: PastaBackend) -> None:
    eml = await pasta.read_eml(HBR)
    assert b"<dataset" in eml
    entities = await pasta.list_entities(HBR)
    by_id = {e.entity_id: e for e in entities}
    assert by_id[THIESSEN].name == "thiessen_weights" and by_id[THIESSEN].size == 734
    assert by_id[THIESSEN].url.endswith(f"/knb-lter-hbr/14/22/{THIESSEN}")
    assert await pasta.entity_checksum(HBR, THIESSEN) == "17fb97e8e14b7fc9f2037927e18224af5c8403c0"
    assert await pasta.package_doi(HBR) == HBR_DOI.pid


async def test_pasta_missing_package_is_not_found(pasta: PastaBackend) -> None:
    with pytest.raises(ToolError) as exc:
        await pasta.read_eml(PackageId("knb-lter-hbr", 2, 999))
    assert exc.value.code == "not_found"
    assert exc.value.details["identifier"] == "knb-lter-hbr.2.999"


async def test_pasta_search(pasta: PastaBackend) -> None:
    page = await pasta.search(SearchQuery(text="streamflow", limit=5))
    assert page.total and page.total > 5 and page.total_exact
    assert len(page.hits) == 5
    first = page.hits[0]
    assert first.package.revision is not None and first.title and first.doi
    assert first.keywords and first.authors
    scoped = await pasta.search(SearchQuery(text="precipitation", scope="knb-lter-hbr", limit=3))
    assert {h.package.scope for h in scoped.hits} == {"knb-lter-hbr"}
    assert any("newest revision" in n for n in pasta.notes)


async def test_pasta_resolves_dois(pasta: PastaBackend, router: FixtureRouter) -> None:
    assert await pasta.resolve_doi(HBR_DOI) == HBR
    # A superseded revision's DOI is not in PASTA search; DataONE's resource map answers.
    assert await pasta.resolve_doi(OLD_DOI) == PackageId("knb-lter-hbr", 14, 21)
    assert any("resolved via DataONE" in n for n in pasta.notes)
    assert pasta.stats.backend == "pasta"


async def test_pasta_unknown_doi_without_fallback(client: EdiClient, router: FixtureRouter) -> None:
    backend = PastaBackend(
        client, Config.model_validate({}), UpstreamStats(), ApiKey(TEST_KEY, "config")
    )
    with pytest.raises(ToolError) as exc:
        await backend.resolve_doi(OLD_DOI)
    assert exc.value.code == "not_found"


# ---------------------------------------------------------------------- DataONE


async def test_dataone_listings(dataone: DataOneBackend) -> None:
    identifiers = await dataone.list_identifiers("knb-lter-hbr")
    assert 14 in identifiers
    revisions = await dataone.list_revisions("knb-lter-hbr", 14)
    assert revisions and revisions == sorted(set(revisions))
    assert dataone.stats.backend == "dataone" and dataone.stats.credential == "none"
    assert any("DataONE replicas" in n for n in dataone.notes)
    with pytest.raises(ToolError) as exc:
        await dataone.list_identifiers("no-such-scope")
    assert exc.value.code == "not_found" and "EDI_API_KEY" in (exc.value.hint or "")


async def test_dataone_search_dedupes_series(dataone: DataOneBackend) -> None:
    page = await dataone.search(SearchQuery(text="streamflow", limit=5))
    assert not page.total_exact and page.total
    series = [h.package.series for h in page.hits]
    assert len(series) == len(set(series))
    assert all(h.package.revision is not None for h in page.hits)
    scoped = await dataone.search(SearchQuery(text="precipitation", scope="knb-lter-hbr", limit=3))
    assert {h.package.scope for h in scoped.hits} == {"knb-lter-hbr"}


async def test_dataone_eml_routes_by_scope(dataone: DataOneBackend, router: FixtureRouter) -> None:
    assert b"<dataset" in await dataone.read_eml(HBR)
    assert router.calls[-1].host == "gmn.lternet.edu"
    assert b"<dataset" in await dataone.read_eml(EDI)
    assert router.calls[-1].host == "gmn.edirepository.org"


async def test_dataone_missing_eml_tries_cn_then_not_found(
    dataone: DataOneBackend, router: FixtureRouter
) -> None:
    with pytest.raises(ToolError) as exc:
        await dataone.read_eml(PackageId("knb-lter-hbr", 2, 20))
    assert exc.value.code == "not_found" and "EDI_API_KEY" in (exc.value.hint or "")
    assert [c.host for c in router.calls[-2:]] == ["gmn.lternet.edu", "cn.dataone.org"]


async def test_dataone_entities(dataone: DataOneBackend) -> None:
    hbr = {e.entity_id: e for e in await dataone.list_entities(HBR)}
    assert hbr[THIESSEN].name == "thiessen_weights"
    assert hbr[THIESSEN].entity_type == "otherEntity"
    assert len(hbr) == 5
    indexed = await dataone.list_entities(EDI)
    assert len(indexed) == 1 and indexed[0].sha1 and indexed[0].size
    assert indexed[0].url.startswith("https://pasta.lternet.edu/package/data/eml/edi/2081/1/")


async def test_dataone_checksum_and_dois(dataone: DataOneBackend) -> None:
    assert (
        await dataone.entity_checksum(HBR, THIESSEN) == "17fb97e8e14b7fc9f2037927e18224af5c8403c0"
    )
    assert await dataone.package_doi(EDI) == "doi:10.6073/pasta/5100e60582808c66095e767be806109f"
    # Not indexed in DataONE yet: the citation service supplies it.
    assert await dataone.package_doi(HBR) == HBR_DOI.pid
    assert any("citation service" in n for n in dataone.notes)
    assert await dataone.resolve_doi(HBR_DOI) == HBR


async def test_dataone_doi_unknown_everywhere(
    dataone: DataOneBackend, router: FixtureRouter
) -> None:
    router.add(
        "GET cite.edirepository.org/cite/knb-lter-hbr.14.22",
        Reply(404, b"not found", "text/plain"),
    )
    router.add(
        "GET cn.dataone.org/cn/v2/query/solr/"
        "?fl=id%2CresourceMap&q=id%3A%22https%3A%2F%2Fpasta.lternet.edu%2Fpackage%2Fmetadata"
        "%2Feml%2Fknb-lter-hbr%2F14%2F22%22&rows=1&wt=json",
        Reply(200, b'{"response":{"numFound":0,"docs":[]}}', "application/json"),
    )
    assert await dataone.package_doi(HBR) is None
    assert any("Neither DataONE" in n for n in dataone.notes)


async def test_dataone_bad_solr_json_is_decode_error(
    dataone: DataOneBackend, router: FixtureRouter
) -> None:
    router.inject(Reply(200, b"<html>maintenance</html>", "text/html"))
    with pytest.raises(Exception) as exc:
        await dataone.list_revisions("knb-lter-hbr", 14)
    assert getattr(exc.value, "kind", None) == "decode"


def test_solr_escape() -> None:
    assert solr_escape("https://a/b-c") == r"https\:\/\/a\/b\-c"


# ---------------------------------------------------------------------- shared


async def test_resolve_package_forms(pasta: PastaBackend, dataone: DataOneBackend) -> None:
    newest = await resolve_package(pasta, "knb-lter-hbr.14")
    assert newest.package == HBR and newest.revision_from == "newest"
    oldest = await resolve_package(pasta, "knb-lter-hbr/14", "oldest")
    assert oldest.package.revision == 6
    given = await resolve_package(dataone, "knb-lter-hbr.14.22")
    assert given.revision_from == "given"
    via_doi = await resolve_package(dataone, f"https://doi.org/{HBR_DOI.doi}")
    assert via_doi.package == HBR and via_doi.revision_from == "doi"
    url = f"https://pasta.lternet.edu/package/data/eml/knb-lter-hbr/14/22/{THIESSEN}"
    assert (await resolve_package(pasta, url)).entity_id == THIESSEN


async def test_resolve_package_errors(pasta: PastaBackend) -> None:
    with pytest.raises(ToolError) as exc:
        await resolve_package(pasta, "knb-lter-hbr.999999")
    assert exc.value.code == "not_found"
    with pytest.raises(ToolError) as exc:
        await resolve_package(pasta, HBR_DOI.pid, 3)
    assert exc.value.code == "invalid_argument"


async def test_backend_for_follows_the_key(key_server: EdiServer, server: EdiServer) -> None:
    key_ctx = key_server.tool_context("edi_ping")
    anon_ctx = server.tool_context("edi_ping")
    pasta = backend_for(key_ctx)
    assert isinstance(pasta, PastaBackend) and key_ctx.stats.backend == "pasta"
    assert isinstance(backend_for(anon_ctx), DataOneBackend)
    assert anon_ctx.stats.backend == "dataone"


# ---------------------------------------------------------------------- search filters


def test_pasta_search_filter() -> None:
    from edi_mcp.edi.backends import BoundingBox
    from edi_mcp.edi.backends.pasta import search_filter

    assert search_filter(SearchQuery()) == "-scope:(ecotrends lter-landsat lter-landsat-ledaps)"
    assert search_filter(SearchQuery(exclude_bulk=False)) is None
    assert search_filter(SearchQuery(scope="ecotrends")) == "scope:ecotrends"
    full = search_filter(
        SearchQuery(
            scope="knb-lter-jrn",
            author="Peters",
            start_year=1990,
            end_year=2000,
            bbox=BoundingBox(-107, 32.4, -106.5, 32.8),
        )
    )
    assert full == (
        'scope:knb-lter-jrn AND author:"Peters" AND begindate:[* TO 2000-12-31T23:59:59Z] '
        "AND enddate:[1990-01-01T00:00:00Z TO *] AND "
        'coordinates:"Intersects(ENVELOPE(-107, -106.5, 32.8, 32.4))"'
    )


def test_dataone_search_filter(dataone: DataOneBackend) -> None:
    from edi_mcp.edi.backends import BoundingBox

    fq = dataone.search_filter(
        SearchQuery(author="likens", start_year=1960, bbox=BoundingBox(-107, 32.4, -106.5, 32.8))
    )
    assert 'investigatorText:"likens"' in fq and "endDate:[1960-01-01T00:00:00Z TO *]" in fq
    assert "beginDate" not in fq
    assert "northBoundCoord:[32.4 TO *] AND southBoundCoord:[* TO 32.8]" in fq
    assert "eastBoundCoord:[-107 TO *] AND westBoundCoord:[* TO -106.5]" in fq
    assert fq.count("-id:") == 3
    assert "-id:" not in dataone.search_filter(SearchQuery(scope="ecotrends"))


@pytest.mark.parametrize(
    "hostile",
    ['Likens" OR *:*', "a\\", 'x") OR scope:(edi', "O'Neil:(x)"],
)
def test_author_cannot_break_out_of_its_phrase(hostile: str, dataone: DataOneBackend) -> None:
    from edi_mcp.edi.backends.base import solr_phrase
    from edi_mcp.edi.backends.pasta import search_filter

    phrase = solr_phrase(hostile)
    inner = phrase[1:-1]
    assert phrase.startswith('"') and phrase.endswith('"')
    assert '"' not in inner and "\\" not in inner
    assert search_filter(SearchQuery(author=hostile)).count('"') == 2
    assert dataone.search_filter(SearchQuery(author=hostile)).count('"') == 6  # + source filter
