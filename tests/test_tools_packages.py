"""Package, metadata and entity tools on both backends, replayed from recorded fixtures."""

from __future__ import annotations

import json
from typing import Any

import pytest

from edi_mcp.edi.backends import EntityInfo
from edi_mcp.projections.eml import EntityMetadata
from edi_mcp.server import EdiServer
from edi_mcp.tools.packages import merge_entities
from tests.fixture_router import FixtureRouter
from tests.helpers import TEST_KEY, call_err, call_ok

HBR = "knb-lter-hbr.14.22"
JRN = "knb-lter-jrn.210548103.32"
THIESSEN = "c4f72fa0cb155f1b61f1333bb67e3d00"
JRN_ENTITY = "9c680810940709cb17bf09e4c4785100"


@pytest.fixture(params=["pasta", "dataone"])
def either(request: pytest.FixtureRequest, server: EdiServer, key_server: EdiServer) -> EdiServer:
    return key_server if request.param == "pasta" else server


def _backend(server: EdiServer) -> str:
    return "pasta" if server.config.key_value() else "dataone"


# ---------------------------------------------------------------------- edi_get_package


async def test_get_package(either: EdiServer) -> None:
    p = await call_ok(either, "edi_get_package", {"package": HBR})
    assert p["packageId"] == HBR and p["series"] == "knb-lter-hbr.14" and p["revision"] == 22
    assert p["revisionFrom"] == "given" and p["resolved"] == []
    assert p["title"].startswith("Hubbard Brook Experimental Forest: Total Daily Precipitation")
    assert p["doi"] == "doi:10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062"
    assert p["doiUrl"] == "https://doi.org/10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062"
    assert p["metadataUrl"] == "https://pasta.lternet.edu/package/metadata/eml/knb-lter-hbr/14/22"
    assert p["creators"] == ["USDA Forest Service, Northern Research Station"]
    assert p["license"]["truncated"] is True and len(p["license"]["text"]) <= 300
    assert p["entityCount"] == 5 and len(p["entities"]) == 5
    by_id = {e["entityId"]: e for e in p["entities"]}
    assert by_id[THIESSEN]["name"] == "thiessen_weights" and by_id[THIESSEN]["size"] == 734
    assert p["totalBytes"] == sum(e["size"] for e in p["entities"])
    assert p["isNewest"] is True and p["newestRevision"] == 22
    assert p["source"]["backend"] == _backend(either)
    assert not any("not matched" in n or "not listed" in n for n in p["notes"])
    assert any("edi_get_metadata" in s for s in p["nextSteps"])


async def test_get_package_newest_of_a_series(key_server: EdiServer) -> None:
    p = await call_ok(key_server, "edi_get_package", {"package": "knb-lter-hbr.14"})
    assert p["packageId"] == HBR and p["revisionFrom"] == "newest" and p["isNewest"] is True
    assert p["resolved"] == [
        {"field": "package", "input": "knb-lter-hbr.14", "code": HBR, "confidence": 1.0}
    ]


async def test_get_package_flags_a_superseded_revision(
    key_server: EdiServer, router: FixtureRouter
) -> None:
    from tests.fixture_router import Reply

    router.add(
        "GET pasta.lternet.edu/package/eml/knb-lter-hbr/14",
        Reply(200, b"21\n22\n23\n", "text/plain"),
    )
    p = await call_ok(key_server, "edi_get_package", {"package": HBR})
    assert p["isNewest"] is False and p["newestRevision"] == 23
    assert any("knb-lter-hbr.14.23" in n for n in p["notes"])


async def test_restricted_package(key_server: EdiServer) -> None:
    error = await call_err(
        key_server, "edi_get_package", {"package": "icarus.13.1"}, "upstream_forbidden"
    )
    assert error["details"]["reason"] == "access_restricted"
    assert "icarus.13.1" in error["message"] and "mistyped" not in error["message"]
    text = json.dumps(error)
    assert "User '…' is not authorized" in error["details"]["upstream"]
    assert TEST_KEY not in text and "(Public Access)" not in text


async def test_get_package_rejects_bad_revisions(server: EdiServer) -> None:
    await call_err(server, "edi_get_package", {"package": HBR, "revision": -1}, "invalid_argument")
    await call_err(server, "edi_get_package", {"package": HBR, "revision": 3}, "invalid_argument")
    await call_err(
        server,
        "edi_get_package",
        {"package": "knb-lter-hbr.14", "revision": "latest"},
        "invalid_argument",
    )


# ---------------------------------------------------------------------- edi_get_metadata


async def test_get_metadata(either: EdiServer) -> None:
    p = await call_ok(either, "edi_get_metadata", {"package": JRN})
    assert p["packageId"] == JRN and p["emlVersion"] == "2.1.0"
    assert p["title"].startswith("Jornada Basin LTER Cross-scale Interactions Study")
    assert p["abstract"].startswith("1-second summary precipitation data")
    assert p["abstractTruncated"] is False
    assert {k["thesaurus"] for k in p["keywords"]} >= {"LTER Controlled Vocabulary"}
    assert p["creators"] and p["contacts"]
    cov = p["coverage"]
    assert cov["geographicTotal"] >= 1 and cov["geographic"][0]["west"] < -100
    assert cov["temporal"][0]["begin"].startswith("2017")
    assert p["methods"]["steps"] >= 1 and p["methods"]["text"]
    assert p["license"]["text"]
    assert p["entitiesTotal"] == 1 and p["entities"][0]["entityId"] == JRN_ENTITY
    assert "attributes" not in p["entities"][0]
    assert p["source"]["backend"] == _backend(either)
    assert len(p["source"]["endpoints"]) == 1  # one EML fetch, nothing else


async def test_get_metadata_sections_and_license(either: EdiServer) -> None:
    p = await call_ok(either, "edi_get_metadata", {"package": "edi.2081.1", "include": ["rights"]})
    assert p["license"]["name"] or p["license"]["url"]
    for absent in ("abstract", "creators", "coverage", "methods", "project", "entities"):
        assert absent not in p
    assert p["title"]  # always present


async def test_get_metadata_cuts_text(server: EdiServer) -> None:
    p = await call_ok(
        server, "edi_get_metadata", {"package": JRN, "include": ["overview"], "max_text_chars": 200}
    )
    assert p["abstractTruncated"] is True and len(p["abstract"]) <= 200
    assert any("Cut at 200 characters: abstract" in n for n in p["notes"])


async def test_get_metadata_rejects_bad_sections(server: EdiServer) -> None:
    await call_err(
        server, "edi_get_metadata", {"package": JRN, "include": ["raw"]}, "invalid_argument"
    )
    await call_err(server, "edi_get_metadata", {"package": JRN, "include": []}, "invalid_argument")
    await call_err(
        server, "edi_get_metadata", {"package": JRN, "max_text_chars": 10}, "invalid_argument"
    )


# ---------------------------------------------------------------------- edi_list_entities


async def test_list_entities(either: EdiServer) -> None:
    p = await call_ok(either, "edi_list_entities", {"package": JRN, "include_checksums": True})
    (entity,) = p["entities"]
    assert entity["entityId"] == JRN_ENTITY and entity["entityType"] == "dataTable"
    assert entity["objectName"] == "csis-15_ppt_detailed_L2_rev_32.csv"
    assert entity["size"] == 359545 and entity["numberOfRecords"] == 6550
    assert entity["sha1"] == "008425fe2f2c430585be11ec0569ce6b67d234cb"
    assert (
        entity["textFormat"]["headerLines"] == 4 and entity["textFormat"]["fieldDelimiter"] == ","
    )
    names = [a["name"] for a in entity["attributes"]]
    assert names[:2] == ["Date", "Year"] and entity["attributesTotal"] == len(names)
    year = entity["attributes"][1]
    assert year["unit"] == "nominalYear" and year["missingValueCodes"][0]["code"] == "NaN"
    assert entity["attributes"][0]["dateFormat"] == "yyyy-MM-dd HH:mm:ss"
    assert entity["dataUrl"] == (
        f"https://pasta.lternet.edu/package/data/eml/knb-lter-jrn/210548103/32/{JRN_ENTITY}"
    )
    assert entity["anonymousUrl"].startswith("https://gmn.lternet.edu/mn/v2/object/https%3A%2F%2F")
    assert entity["anonymousUrl"].endswith(f"%2F32%2F{JRN_ENTITY}")
    assert p["page"]["total"] == 1 and p["source"]["backend"] == _backend(either)
    assert any("edi_preview_entity" in s for s in p["nextSteps"])


async def test_list_entities_filters_by_name(either: EdiServer) -> None:
    p = await call_ok(either, "edi_list_entities", {"package": HBR, "entity": "Thiessen_Weights"})
    assert [e["entityId"] for e in p["entities"]] == [THIESSEN]
    assert p["entities"][0]["entityType"] == "otherEntity"


async def test_list_entities_unknown_entity(key_server: EdiServer) -> None:
    error = await call_err(
        key_server, "edi_list_entities", {"package": HBR, "entity": "nope"}, "not_found"
    )
    assert error["details"] == {"identifier": "nope", "packageId": HBR}


async def test_list_entities_elides_attributes_to_fit_the_budget(
    make_server: Any, config: Any
) -> None:
    small = config.model_copy(deep=True)
    small.limits.max_result_bytes = 3000
    server = make_server(key=TEST_KEY, config=small)
    p = await call_ok(server, "edi_list_entities", {"package": JRN})
    assert p["attributesElided"] is True and p["entities"][0]["attributes"] is None
    assert p["entities"][0]["attributesTotal"] > 0


# ---------------------------------------------------------------------- merge


def _meta(entity_id: str | None, name: str | None) -> EntityMetadata:
    return EntityMetadata(entity_id=entity_id, name=name, entity_type="dataTable")


def test_merge_pairs_by_id_then_name_and_reports_the_rest() -> None:
    infos = [
        EntityInfo(entity_id="a" * 32, name="one"),
        EntityInfo(entity_id="b" * 32, name="two"),  # id differs, name matches
        EntityInfo(entity_id="c" * 32, name="three"),  # only in the repository
    ]
    metas = [_meta("a" * 32, "one"), _meta("x" * 32, "two"), _meta("y" * 32, "four")]
    pairs, notes = merge_entities(infos, metas)
    assert [(m.name if m else None, i.name if i else None) for m, i in pairs] == [
        ("one", "one"),
        ("two", "two"),
        (None, "three"),
        ("four", None),
    ]
    assert any("three" in n and "not matched" in n for n in notes)
    assert any("four" in n and "not listed" in n for n in notes)
    assert merge_entities([], metas)[1] == []


@pytest.mark.parametrize("tool", ["edi_get_package", "edi_list_entities"])
async def test_dataone_fetches_the_eml_once(
    make_server: Any, config: Any, router: FixtureRouter, tool: str
) -> None:
    uncached = config.model_copy(deep=True)
    uncached.cache.enabled = False  # as when recording: a second fetch would really go out
    await call_ok(make_server(config=uncached), tool, {"package": HBR})
    eml_calls = [c for c in router.calls if c.host == "gmn.lternet.edu" and "/object/" in c.url]
    assert len(eml_calls) == 1
