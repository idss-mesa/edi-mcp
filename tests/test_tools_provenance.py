"""Citation, quality report, lineage and feed tools, replayed from recorded fixtures."""

from __future__ import annotations

import json
import re

import pytest

from edi_mcp.server import EdiServer
from tests.fixture_router import FixtureRouter, Reply
from tests.helpers import call_err, call_ok

HBR = "knb-lter-hbr.14.22"
HBR_DOI = "doi:10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062"
CHANGES = {"from_date": "2026-10-12", "to_date": "2026-10-18", "scope": "edi"}


@pytest.fixture(params=["pasta", "dataone"])
def either(request: pytest.FixtureRequest, server: EdiServer, key_server: EdiServer) -> EdiServer:
    return key_server if request.param == "pasta" else server


# ---------------------------------------------------------------------- edi_get_citation


async def test_citation_esip(either: EdiServer) -> None:
    p = await call_ok(either, "edi_get_citation", {"package": HBR})
    assert p["style"] == "ESIP" and p["packageId"] == HBR
    assert p["citation"].startswith("USDA Forest Service, Northern Research Station. 2026.")
    assert p["citation"].endswith("2017345f0977c0f7c46e1ad90ce1b062.")
    parts = p["parts"]
    assert parts["doi"] == HBR_DOI and parts["year"] == "2026" and parts["version"] == "ver 22"
    assert parts["publisher"] == "Environmental Data Initiative"
    assert p["doiUrl"] == "https://doi.org/10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062"
    assert "mapbrowse?scope=knb-lter-hbr&identifier=14&revision=22" in p["portalUrl"]
    assert p["source"]["backend"] == "cite"
    assert any("edi-policy" in n for n in p["notes"])


async def test_citation_bibtex(key_server: EdiServer) -> None:
    p = await call_ok(key_server, "edi_get_citation", {"package": HBR, "style": "BIBTEX"})
    assert p["citation"].startswith("@misc{knb-lter-hbr.14.22,")
    assert "doi={10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062}" in p["citation"]


async def test_citation_of_a_series_reports_mixed_sources(
    key_server: EdiServer, router: FixtureRouter
) -> None:
    router.add("GET pasta.lternet.edu/package/eml/knb-lter-hbr/14", Reply(200, b"21\n22\n"))
    p = await call_ok(key_server, "edi_get_citation", {"package": "knb-lter-hbr.14"})
    assert p["packageId"] == HBR and p["revisionFrom"] == "newest"
    assert p["source"]["backend"] == "mixed"


async def test_citation_of_a_restricted_or_missing_package(server: EdiServer) -> None:
    error = await call_err(server, "edi_get_citation", {"package": "icarus.13.1"}, "not_found")
    assert "<" not in error["message"] and "access-restricted" in error["hint"]


# ---------------------------------------------------------------------- edi_get_quality_report


async def test_quality_report(either: EdiServer) -> None:
    p = await call_ok(either, "edi_get_quality_report", {"package": "edi.2081.1"})
    assert p["created"] == "2025-07-21T19:21:35"
    assert p["counts"] == {"valid": 20, "info": 8, "warn": 1, "error": 0}
    assert p["issuesTotal"] == 1
    (issue,) = p["issues"]
    assert issue["identifier"] == "fundingPresence" and issue["status"] == "warn"
    assert "entity" not in issue and issue["suggestion"] == "Include the funding source, please."
    assert p["entitiesTotal"] == 1 and p["entities"][0]["name"] == "EDS_Course_Materials"
    expected = "pasta" if either.config.key_value() else "dataone"
    assert p["source"]["backend"] == expected


async def test_quality_report_with_info_checks(server: EdiServer) -> None:
    p = await call_ok(
        server, "edi_get_quality_report", {"package": "edi.2081.1", "include_info": True}
    )
    assert p["issuesTotal"] == 9 and p["issues"][0]["status"] == "warn"
    assert {i["status"] for i in p["issues"][1:]} == {"info"}
    assert any(i.get("entity") == "EDS_Course_Materials" for i in p["issues"])


# ---------------------------------------------------------------------- edi_get_lineage


async def test_lineage(key_server: EdiServer) -> None:
    p = await call_ok(key_server, "edi_get_lineage", {"package": HBR})
    (src,) = p["sources"]
    assert src["packageId"] == "knb-lter-hbr.278.8"
    # The double-escaped title is decoded.
    assert src["title"] == (
        "Hubbard Brook Experimental Forest: 15-minute Precipitation by Watershed, 2017 - present"
    )
    assert p["descendants"] == []
    assert p["nextSteps"] == ["edi_get_package(package='knb-lter-hbr.278.8')"]


async def test_key_only_tools_fail_fast_without_a_key(
    server: EdiServer, router: FixtureRouter
) -> None:
    for tool, args in (
        ("edi_get_lineage", {"package": HBR}),
        ("edi_recent_changes", {}),
        ("edi_get_read_counts", {"package": "edi.2081"}),
    ):
        error = await call_err(server, tool, args, "auth_required")
        assert "edi://guide/api-key" in json.dumps(error)
    assert router.calls == []


# ---------------------------------------------------------------------- edi_recent_changes


async def test_recent_changes(key_server: EdiServer) -> None:
    p = await call_ok(key_server, "edi_recent_changes", CHANGES)
    assert p["fromDate"] == "2026-10-12" and p["toDate"] == "2026-10-18" and p["scope"] == "edi"
    dates = [c["date"] for c in p["changes"]]
    assert dates == sorted(dates, reverse=True) and len(dates) == p["page"]["total"] == 5
    assert all(c["packageId"].startswith("edi.") for c in p["changes"])
    assert p["changes"][0] == {
        "packageId": "edi.1509.22",
        "kind": "update",
        "date": "2026-10-16T16:01:33Z",
        "doi": "doi:10.6073/pasta/3f251264696182edc3c8bbfed5b37e18",
    }
    assert sum(p["counts"].values()) == 5
    # The upstream feed names each uploader's principal; no result ever does.
    assert not re.search(r"EDI-[0-9a-f]{40}|principal", json.dumps(p))


async def test_recent_changes_filters_and_validates(key_server: EdiServer) -> None:
    p = await call_ok(key_server, "edi_recent_changes", {**CHANGES, "kinds": ["update"]})
    assert {c["kind"] for c in p["changes"]} == {"update"} and p["page"]["total"] == 2
    assert sum(p["counts"].values()) == 5  # counts describe the whole window
    await call_err(
        key_server,
        "edi_recent_changes",
        {"from_date": "2026-01-01", "to_date": "2026-10-18"},
        "invalid_argument",
    )
    await call_err(
        key_server,
        "edi_recent_changes",
        {"from_date": "2026-10-18", "to_date": "2026-10-12"},
        "invalid_argument",
    )


# ---------------------------------------------------------------------- edi_get_read_counts


async def test_read_counts_of_a_series(key_server: EdiServer) -> None:
    p = await call_ok(key_server, "edi_get_read_counts", {"package": "edi.2081"})
    assert p["series"] == "edi.2081" and "revision" not in p
    assert {"dataPackage", "metadata", "report", "data", "archive"} <= set(p["totals"])
    assert p["revisionsTotal"] == 1 and p["revisions"][0]["revision"] == 1
    rev = p["revisions"][0]
    assert rev["package"]["total"] == p["totals"]["dataPackage"]["total"]
    assert rev["data"]["total"] == p["totals"]["data"]["total"]
    assert all(t["nonRobot"] <= t["total"] for t in p["totals"].values())


async def test_read_counts_of_one_revision(key_server: EdiServer) -> None:
    p = await call_ok(key_server, "edi_get_read_counts", {"package": "knb-lter-jrn.210548103.32"})
    assert p["series"] == "knb-lter-jrn.210548103" and p["revision"] == 32
    assert [r["revision"] for r in p["revisions"]] == [32]
    assert p["nextSteps"] == ["edi_get_citation(package='knb-lter-jrn.210548103.32')"]


async def test_dataone_newest_is_qualified_in_citations(server: EdiServer) -> None:
    p = await call_ok(server, "edi_get_citation", {"package": "knb-lter-hbr.14"})
    assert p["packageId"] == HBR and p["revisionFrom"] == "newest"
    assert any("newest DataONE holds" in n for n in p["notes"])
    assert p["source"]["backend"] == "mixed"


async def test_dataone_newest_is_qualified_in_quality_reports(
    server: EdiServer, router: FixtureRouter
) -> None:
    router.add(
        "GET gmn.lternet.edu/mn/v2/object/"
        "https%3A%2F%2Fpasta.lternet.edu%2Fpackage%2Freport%2Feml%2Fknb-lter-hbr%2F14%2F22",
        Reply(200, b"<qualityReport><packageId>knb-lter-hbr.14.22</packageId></qualityReport>"),
    )
    p = await call_ok(server, "edi_get_quality_report", {"package": "knb-lter-hbr.14"})
    assert p["packageId"] == HBR and p["revisionFrom"] == "newest"
    assert any("newest DataONE holds" in n for n in p["notes"])
