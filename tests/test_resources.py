from __future__ import annotations

import json
import re
from typing import Any

import pytest

from edi_mcp.errors import ToolError
from edi_mcp.instructions import SERVER_INSTRUCTIONS
from edi_mcp.prompts import PROMPTS, get_prompt
from edi_mcp.registry import get_registered_tools
from edi_mcp.resources import (
    DERIVED_TTL_MS,
    STATIC_DIR,
    STATIC_TTL_MS,
    list_resource_templates,
    list_resources,
    read_resource,
)
from edi_mcp.server import EdiServer


def test_listing_is_sorted_and_tagged() -> None:
    resources = list_resources()
    uris = [str(r.uri) for r in resources]
    assert uris == sorted(uris)
    assert uris == [
        "edi://guide/agent-workflow",
        "edi://guide/api-key",
        "edi://guide/citing-edi-data",
        "edi://guide/package-identifiers",
        "edi://guide/search-syntax",
        "edi://reference/scopes",
    ]
    assert all((r.meta or {})["io.edi-mcp/kind"] == "static" for r in resources)
    assert [t.uri_template for t in list_resource_templates()] == [
        "edi://packages/{packageId}",
        "edi://packages/{packageId}/eml",
    ]


async def test_static_reads(server: EdiServer) -> None:
    ctx = server.tool_context("resources/read")
    for resource in list_resources():
        content = await read_resource(str(resource.uri), ctx)
        assert content.ttl_ms == STATIC_TTL_MS and content.text.strip()
    key_guide = (await read_resource("edi://guide/api-key", ctx)).text
    for phrase in ("2026-07-30", "auth/ui/key", "EDI_API_KEY", "X-EDI-Key", "upstream_forbidden"):
        assert phrase in key_guide
    for phrase in ("access_restricted",):
        assert phrase in key_guide
    ids = (await read_resource("edi://guide/package-identifiers", ctx)).text
    assert "knb-lter-hbr.14.22" in ids and "doi:10.6073/pasta/" in ids
    search = (await read_resource("edi://guide/search-syntax", ctx)).text
    assert "OR" in search and "include_bulk" in search
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
        "edi://guide/agent-workflow",
    ):
        assert phrase in SERVER_INSTRUCTIONS


HBR = "knb-lter-hbr.14.22"


@pytest.fixture(params=["pasta", "dataone"])
def either(request: pytest.FixtureRequest, server: EdiServer, key_server: EdiServer) -> EdiServer:
    return key_server if request.param == "pasta" else server


async def test_package_template(either: EdiServer) -> None:
    content = await read_resource(f"edi://packages/{HBR}", either.tool_context("resources/read"))
    payload = json.loads(content.text)
    assert payload["packageId"] == HBR and payload["entityCount"] == 5
    assert content.mime_type == "application/json" and content.ttl_ms == DERIVED_TTL_MS
    assert content.cache_scope == "private"  # depends on the caller's key (D21)


async def test_eml_template(either: EdiServer) -> None:
    content = await read_resource(
        f"edi://packages/{HBR}/eml", either.tool_context("resources/read")
    )
    assert content.mime_type == "application/xml" and content.cache_scope == "private"
    assert "<eml:eml" in content.text and 'packageId="knb-lter-hbr.14.22"' in content.text


async def test_eml_template_limits_and_errors(make_server: Any, config: Any) -> None:
    cfg = config.model_copy(deep=True)
    cfg.limits.max_resource_bytes = 1024
    small = make_server(config=cfg)
    with pytest.raises(ToolError) as too_big:
        await read_resource(f"edi://packages/{HBR}/eml", small.tool_context("resources/read"))
    assert too_big.value.code == "result_too_large" and "edi_get_metadata" in (
        too_big.value.hint or ""
    )
    anon = make_server()
    ctx = anon.tool_context("resources/read")
    with pytest.raises(ToolError) as restricted:
        await read_resource("edi://packages/icarus.13.1/eml", ctx)
    assert restricted.value.code == "auth_required"
    with pytest.raises(ToolError) as bad:
        await read_resource("edi://packages/not%20a%20package/eml", ctx)
    assert bad.value.code == "invalid_argument"


async def test_templates_over_http(http_server: EdiServer) -> None:
    from tests.helpers.asgi import AppHarness, rpc

    async with AppHarness(http_server) as client:
        _, read = await rpc(client, "resources/read", {"uri": f"edi://packages/{HBR}"})
        _, static = await rpc(client, "resources/read", {"uri": "edi://guide/search-syntax"})
    assert read["result"]["cacheScope"] == "private"
    assert static["result"]["cacheScope"] == "public"


_TOOL_NAME_RE = re.compile(r"\bedi_[a-z_]+\b")


def test_guides_and_prompts_name_only_real_tools() -> None:
    known = {spec.name for spec in get_registered_tools(transport="stdio")} | {
        p.name for p in PROMPTS
    }
    texts = {f.name: f.read_text(encoding="utf-8") for f in STATIC_DIR.glob("*.md")}
    samples = {
        "edi_find_data": {"question": "q", "place": "Jornada", "years": "1990-2000"},
        "edi_cite_package": {"package": HBR, "style": "bibtex"},
        "edi_plan_download": {"package": HBR, "entities": "a, b"},
    }
    for name, args in samples.items():
        texts[name] = get_prompt(name, args).messages[0].content.text  # type: ignore[union-attr]
    texts["instructions"] = SERVER_INSTRUCTIONS
    for label, text in texts.items():
        unknown = set(_TOOL_NAME_RE.findall(text)) - known - {"edi_mcp"}
        assert not unknown, f"{label} names unknown tools {sorted(unknown)}"
