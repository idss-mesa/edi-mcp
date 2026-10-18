from __future__ import annotations

import json

import pytest

from edi_mcp.errors import ToolError
from edi_mcp.instructions import SERVER_INSTRUCTIONS
from edi_mcp.resources import STATIC_TTL_MS, list_resource_templates, list_resources, read_resource
from edi_mcp.server import EdiServer


def test_listing_is_sorted_and_tagged() -> None:
    resources = list_resources()
    uris = [str(r.uri) for r in resources]
    assert uris == sorted(uris)
    assert uris == [
        "edi://guide/api-key",
        "edi://guide/package-identifiers",
        "edi://reference/scopes",
    ]
    assert all((r.meta or {})["io.edi-mcp/kind"] == "static" for r in resources)
    assert list_resource_templates() == []


async def test_static_reads(server: EdiServer) -> None:
    ctx = server.tool_context("resources/read")
    for resource in list_resources():
        content = await read_resource(str(resource.uri), ctx)
        assert content.ttl_ms == STATIC_TTL_MS and content.text.strip()
    key_guide = (await read_resource("edi://guide/api-key", ctx)).text
    for phrase in ("2026-07-30", "auth/ui/key", "EDI_API_KEY", "X-EDI-Key", "upstream_forbidden"):
        assert phrase in key_guide
    ids = (await read_resource("edi://guide/package-identifiers", ctx)).text
    assert "knb-lter-hbr.14.22" in ids and "doi:10.6073/pasta/" in ids
    scopes = json.loads((await read_resource("edi://reference/scopes", ctx)).text)
    jrn = next(s for s in scopes["scopes"] if s["scope"] == "knb-lter-jrn")
    assert jrn["name"] == "Jornada Basin LTER" and jrn["siteCode"] == "JRN"


async def test_unknown_resource_suggests(server: EdiServer) -> None:
    ctx = server.tool_context("resources/read")
    with pytest.raises(ToolError) as exc:
        await read_resource("edi://guide/apikey", ctx)
    assert exc.value.code == "not_found"
    assert "edi://guide/api-key" in exc.value.details["didYouMean"]


def test_instructions() -> None:
    assert len(SERVER_INSTRUCTIONS) <= 1200
    for phrase in (
        "edi_search_packages",
        "EDI_API_KEY",
        "auth_required",
        "edi://guide/api-key",
        "edi_ping",
        "source.backend",
        "site codes",
    ):
        assert phrase in SERVER_INSTRUCTIONS
