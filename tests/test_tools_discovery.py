"""Discovery tools on both backends, replayed from recorded fixtures."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from edi_mcp.server import EdiServer
from tests.fixture_router import FixtureRouter
from tests.helpers import TEST_KEY, call_err, call_ok

FILTERS: dict[str, Any] = {
    "author": "likens",
    "start_year": 1960,
    "end_year": 1970,
    "sort": "newest",
    "limit": 5,
}
JORNADA_BOX = [-107, 32.4, -106.5, 32.8]


@pytest.fixture(params=["pasta", "dataone"])
def either(request: pytest.FixtureRequest, server: EdiServer, key_server: EdiServer) -> EdiServer:
    return key_server if request.param == "pasta" else server


def _backend(server: EdiServer) -> str:
    return "pasta" if server.config.key_value() else "dataone"


# ---------------------------------------------------------------------- search


async def test_search_returns_compact_hits(either: EdiServer) -> None:
    payload = await call_ok(either, "edi_search_packages", {"query": "streamflow", "limit": 5})
    assert payload["source"]["backend"] == _backend(either)
    assert payload["page"]["limit"] == 5 and 0 < payload["page"]["returned"] <= 5
    hit = payload["items"][0]
    assert hit["packageId"].count(".") == 2 and hit["title"]
    assert hit["portalUrl"].startswith("https://portal.edirepository.org/nis/mapbrowse?scope=")
    assert len(hit["authors"]) <= 5 and len(hit["keywords"]) <= 10
    assert payload["page"]["nextOffset"] == 5
    assert any("edi_get_package" in s for s in payload["nextSteps"])
    assert any("offset=5" in s for s in payload["nextSteps"])
    # Bulk scopes are excluded by default.
    assert not any(
        h["packageId"].startswith(("ecotrends.", "lter-landsat")) for h in payload["items"]
    )


async def test_search_totals_are_exact_only_on_pasta(either: EdiServer) -> None:
    payload = await call_ok(either, "edi_search_packages", {"query": "streamflow", "limit": 5})
    exact = _backend(either) == "pasta"
    assert payload["totalExact"] is exact
    assert any("upper bound" in n for n in payload["notes"]) is not exact


async def test_search_resolves_a_scope_name(either: EdiServer) -> None:
    payload = await call_ok(
        either,
        "edi_search_packages",
        {"query": "precipitation", "scope": "Hubbard Brook", "limit": 3},
    )
    assert payload["resolved"] == [
        {"field": "scope", "input": "Hubbard Brook", "code": "knb-lter-hbr", "confidence": 0.95}
    ]
    assert {h["packageId"].split(".")[0] for h in payload["items"]} == {"knb-lter-hbr"}


async def test_search_filters(either: EdiServer) -> None:
    payload = await call_ok(either, "edi_search_packages", FILTERS)
    assert payload["items"] and payload["page"]["total"] >= len(payload["items"])
    for hit in payload["items"]:
        assert hit["beginDate"][:4] <= "1970" and hit["endDate"][:4] >= "1960"
    dates = [h["pubDate"] for h in payload["items"] if h.get("pubDate")]
    assert dates == sorted(dates, reverse=True)


async def test_search_bbox(either: EdiServer) -> None:
    payload = await call_ok(either, "edi_search_packages", {"bbox": JORNADA_BOX, "limit": 5})
    scopes = [h["packageId"].split(".")[0] for h in payload["items"]]
    assert scopes.count("knb-lter-jrn") >= 3


async def test_dataone_pages_advance_by_rows_not_hits(server: EdiServer) -> None:
    payload = await call_ok(
        server, "edi_search_packages", {"query": "thiessen", "scope": "HBR", "limit": 3}
    )
    page = payload["page"]
    # Three Solr rows collapsed to fewer packages; the next page starts at row 3.
    assert page["returned"] < 3 and page["nextOffset"] == 3 and page["truncated"] is True
    assert payload["resolved"][0]["code"] == "knb-lter-hbr"


async def test_search_notes_unreplicated_scopes(server: EdiServer) -> None:
    payload = await call_ok(server, "edi_search_packages", {"scope": "Seattle", "limit": 3})
    assert payload["items"] == [] and payload["resolved"][0]["code"] == "cos-spu"
    assert any("does not replicate scope cos-spu" in n for n in payload["notes"])
    assert any("Broaden" in s for s in payload["nextSteps"])


@pytest.mark.parametrize(
    "args",
    [
        {"start_year": 2000, "end_year": 1990},
        {"bbox": [-106, 32, -107, 33]},
        {"bbox": [-107, 33, -106, 32]},
        {"bbox": [-200, 32, -106, 33]},
        {"bbox": [-107, -95, -106, 33]},
        {"bbox": [1, 2, 3]},
        {"limit": 51},
        {"sort": "random"},
    ],
)
async def test_search_rejects_bad_arguments(server: EdiServer, args: dict[str, Any]) -> None:
    await call_err(server, "edi_search_packages", args, "invalid_argument")


async def test_search_ambiguous_scope(server: EdiServer, router: FixtureRouter) -> None:
    error = await call_err(server, "edi_search_packages", {"scope": "Alaska"}, "ambiguous_input")
    assert len(error["details"]["candidates"]) == 4
    assert router.calls == []


# ---------------------------------------------------------------------- scopes


async def test_list_scopes_live_with_a_key(key_server: EdiServer) -> None:
    payload = await call_ok(key_server, "edi_list_scopes")
    assert payload["live"] is True and payload["source"]["backend"] == "pasta"
    by_scope = {s["scope"]: s for s in payload["scopes"]}
    assert by_scope["knb-lter-jrn"]["name"] == "Jornada Basin LTER"
    assert by_scope["knb-lter-jrn"]["siteCode"] == "JRN"
    assert by_scope["cos-spu"]["dataonePackages"] == 0
    assert payload["page"]["total"] == len(payload["scopes"]) == 41


async def test_list_scopes_snapshot_without_a_key(server: EdiServer, router: FixtureRouter) -> None:
    payload = await call_ok(server, "edi_list_scopes", {"kind": "bulk"})
    assert payload["live"] is False and router.calls == []
    assert payload["source"]["backend"] == "local"
    assert [s["scope"] for s in payload["scopes"]] == [
        "ecotrends",
        "lter-landsat",
        "lter-landsat-ledaps",
    ]
    assert any("snapshot" in n for n in payload["notes"])


async def test_list_scopes_merges_new_live_scopes(
    key_server: EdiServer, router: FixtureRouter
) -> None:
    from tests.fixture_router import Reply

    router.add("GET pasta.lternet.edu/package/eml", Reply(200, b"edi\nnew-scope\n", "text/plain"))
    payload = await call_ok(key_server, "edi_list_scopes")
    assert payload["scopes"] == [
        {
            "scope": "edi",
            "name": "Environmental Data Initiative",
            "kind": "edi",
            "pastaPackages": 2111,
            "dataonePackages": 1970,
        },
        {"scope": "new-scope", "kind": "unknown"},
    ]
    assert any("no longer listed" in n for n in payload["notes"])


# ---------------------------------------------------------------------- identifiers


async def test_list_identifiers(either: EdiServer) -> None:
    payload = await call_ok(either, "edi_list_identifiers", {"scope": "hbr", "limit": 50})
    assert payload["scope"] == "knb-lter-hbr" and payload["resolved"][0]["confidence"] == 1.0
    ids = payload["identifiers"]
    assert len(ids) == 50 and ids == sorted(ids) and 14 in ids
    assert payload["page"]["nextOffset"] == 50 and payload["page"]["total"] > 300
    assert payload["nextSteps"][0] == f"edi_list_revisions(package='knb-lter-hbr.{ids[0]}')"


async def test_list_identifiers_last_page(server: EdiServer) -> None:
    first = await call_ok(server, "edi_list_identifiers", {"scope": "knb-lter-hbr"})
    total = first["page"]["total"]
    last = await call_ok(
        server, "edi_list_identifiers", {"scope": "knb-lter-hbr", "offset": total - 2}
    )
    assert last["page"]["returned"] == 2 and "nextOffset" not in last["page"]


async def test_list_identifiers_unknown_scope(either: EdiServer) -> None:
    scope = "knb-lter-zzz" if _backend(either) == "pasta" else "no-such-scope"
    error = await call_err(either, "edi_list_identifiers", {"scope": scope}, "not_found")
    assert error["details"]["identifier"] == scope


# ---------------------------------------------------------------------- revisions


async def test_list_revisions(either: EdiServer) -> None:
    payload = await call_ok(either, "edi_list_revisions", {"package": "knb-lter-hbr.14"})
    assert payload["series"] == "knb-lter-hbr.14" and payload["identifier"] == 14
    revisions = payload["revisions"]
    assert revisions == sorted(revisions) and payload["newest"] == revisions[-1]
    assert payload["oldest"] == revisions[0]
    assert payload["newestPackageId"] == f"knb-lter-hbr.14.{revisions[-1]}"
    if _backend(either) == "pasta":
        assert revisions == list(range(6, 23))
    else:
        assert any("DataONE replicas" in n for n in payload["notes"])


async def test_list_revisions_from_a_site_code(either: EdiServer) -> None:
    payload = await call_ok(either, "edi_list_revisions", {"package": "jrn.210548103"})
    assert payload["series"] == "knb-lter-jrn.210548103"
    assert payload["resolved"][0]["code"] == "knb-lter-jrn" and payload["revisions"]


async def test_list_revisions_from_a_doi(key_server: EdiServer) -> None:
    doi = "https://doi.org/10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062"
    payload = await call_ok(key_server, "edi_list_revisions", {"package": doi})
    assert payload["series"] == "knb-lter-hbr.14"
    assert payload["resolved"] == [
        {"field": "package", "input": doi, "code": "knb-lter-hbr.14.22", "confidence": 1.0}
    ]


async def test_list_revisions_notes_an_unlisted_revision(key_server: EdiServer) -> None:
    payload = await call_ok(key_server, "edi_list_revisions", {"package": "knb-lter-hbr.14.3"})
    assert any("Revision 3 is not among" in n for n in payload["notes"])


async def test_list_revisions_not_found(key_server: EdiServer) -> None:
    error = await call_err(
        key_server, "edi_list_revisions", {"package": "knb-lter-hbr.999999"}, "not_found"
    )
    assert error["details"] == {"identifier": "knb-lter-hbr.999999", "backend": "pasta"}


async def test_list_revisions_bad_reference(server: EdiServer) -> None:
    await call_err(server, "edi_list_revisions", {"package": "not a package"}, "invalid_argument")


# ---------------------------------------------------------------------- shared


async def test_results_never_carry_the_key(
    make_server: Callable[..., EdiServer], router: FixtureRouter
) -> None:
    server = make_server(key=TEST_KEY)
    for name, args in [
        ("edi_search_packages", FILTERS),
        ("edi_list_scopes", {}),
        ("edi_list_identifiers", {"scope": "hbr"}),
        ("edi_list_revisions", {"package": "knb-lter-hbr.14"}),
    ]:
        outcome = await server.call(name, args)
        text = json.dumps(outcome.payload)
        assert TEST_KEY not in text and "edi-token" not in text
