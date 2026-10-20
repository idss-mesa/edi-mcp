"""Conformance with the MCP 2026-07-28 stateless core (DESIGN.md section 7.5).

Tool-surface checks run without a transport; wire checks drive the real
Streamable HTTP app (lifespan included) through an ASGI transport.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator

import jsonschema
import pytest
from mcp.types import LATEST_PROTOCOL_VERSION
from pydantic import Field

from edi_mcp.config import Config
from edi_mcp.context import ToolContext
from edi_mcp.errors import InputRequired
from edi_mcp.models.common import EdiInput, ToolResultBase
from edi_mcp.registry import SURFACES, register_tool, unregister_tool
from edi_mcp.server import (
    JSON_SCHEMA_DIALECT,
    META_ENDPOINTS,
    META_REQUIRES_KEY,
    META_SURFACE,
    META_UPSTREAM,
    RESOURCE_READ_STATIC_TTL_MS,
    TOOLS_LIST_TTL_MS,
    EdiServer,
)
from tests.helpers.asgi import AppHarness, mcp_headers, rpc

SERVER_INFO = "io.modelcontextprotocol/serverInfo"
#: PASTA-only tools (DESIGN.md D3); they need an EDI API key. Quality reports are
#: replicated to the DataONE member nodes, so edi_get_quality_report needs none (D18).
KEY_TOOLS = {
    "edi_get_lineage",
    "edi_recent_changes",
    "edi_get_read_counts",
    "edi_download_package",
}
#: Tools that write local files (stdio only, readOnlyHint false).
WRITE_TOOLS = {"edi_download_entities", "edi_download_package"}


# ---------------------------------------------------------------------------
# Tool surface
# ---------------------------------------------------------------------------


def test_schemas_declare_and_satisfy_2020_12(server: EdiServer) -> None:
    for tool in server.tool_definitions():
        for schema in (tool.input_schema, tool.output_schema):
            assert schema is not None and schema["$schema"] == JSON_SCHEMA_DIALECT
            jsonschema.Draft202012Validator.check_schema(schema)


def test_annotations_meta_and_descriptions(server: EdiServer) -> None:
    for tool in server.tool_definitions():
        assert re.match(r"^edi_[a-z_]+$", tool.name)
        ann = tool.annotations
        assert ann is not None and ann.title
        assert None not in (
            ann.read_only_hint,
            ann.destructive_hint,
            ann.idempotent_hint,
            ann.open_world_hint,
        )
        assert ann.destructive_hint is False
        assert ann.read_only_hint is (tool.name not in WRITE_TOOLS)
        meta = tool.meta or {}
        assert meta[META_SURFACE] in SURFACES
        assert meta[META_REQUIRES_KEY] is (tool.name in KEY_TOOLS)
        assert isinstance(meta[META_ENDPOINTS], list)
        assert tool.description and len(tool.description) <= 600
        assert re.search(r"Next: [^\n]+$", tool.description)


def test_tools_list_is_sorted_stable_and_bounded(server: EdiServer) -> None:
    first = [t.model_dump(by_alias=True, exclude_none=True) for t in server.tool_definitions()]
    second = [t.model_dump(by_alias=True, exclude_none=True) for t in server.tool_definitions()]
    assert first == second
    assert [t["name"] for t in first] == sorted(t["name"] for t in first)
    size = len(json.dumps({"tools": first}, separators=(",", ":")))
    assert size <= server.config.limits.tools_list_max_bytes, size


def test_input_models_accept_aliases_and_reject_unknowns(server: EdiServer) -> None:
    for spec in server.tools:
        assert spec.input_model.model_config.get("extra") == "forbid"
        assert spec.input_model.model_config.get("populate_by_name") is True


# ---------------------------------------------------------------------------
# Wire
# ---------------------------------------------------------------------------


class ElicitIn(EdiInput):
    note: str | None = Field(None, description="Ignored.")


class ElicitOut(ToolResultBase):
    choice: str


@pytest.fixture
def conformance_tool() -> Iterator[None]:
    async def handler(args: ElicitIn, ctx: ToolContext) -> ElicitOut:
        if ctx.elicited is None:
            if not ctx.elicitation_supported:
                return ElicitOut(choice="fallback")
            raise InputRequired(
                key="choice",
                message="Pick a colour",
                requested_schema={
                    "type": "object",
                    "properties": {"choice": {"type": "string", "enum": ["red", "blue"]}},
                    "required": ["choice"],
                },
                state={"field": "choice", "candidates": ["red", "blue"]},
            )
        answer = ctx.elicited.responses["choice"]
        content = answer.get("content", answer)
        if content["choice"] not in ctx.elicited.state["candidates"]:
            raise ValueError("stale candidate")
        return ElicitOut(choice=content["choice"])

    register_tool(
        "edi__conformance_elicit",
        title="Conformance",
        description="Test only. Next: none.",
        input_model=ElicitIn,
        output_model=ElicitOut,
        surface="core",
        endpoints=[],
        supports_mrtr=True,
    )(handler)
    yield
    unregister_tool("edi__conformance_elicit")


async def test_stateless_tools_list_with_cache_hint(http_server: EdiServer) -> None:
    async with AppHarness(http_server) as client:
        response, message = await rpc(client, "tools/list")
    assert response.status_code == 200
    assert "mcp-session-id" not in {k.lower() for k in response.headers}
    result = message["result"]
    assert result["ttlMs"] == TOOLS_LIST_TTL_MS and result["cacheScope"] == "public"


async def test_server_discover(http_server: EdiServer) -> None:
    async with AppHarness(http_server) as client:
        _, message = await rpc(client, "server/discover")
    result = message["result"]
    assert LATEST_PROTOCOL_VERSION in result["supportedVersions"]
    assert {"tools", "resources"} <= set(result["capabilities"])
    assert "edi_search_packages" in result["instructions"]
    assert "EDI_API_KEY" in result["instructions"]
    assert result["cacheScope"] == "public" and result["ttlMs"] > 0


async def test_legacy_era_establishes_no_session(http_server: EdiServer) -> None:
    async with AppHarness(http_server) as client:
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert response.status_code == 200
    assert "mcp-session-id" not in {k.lower() for k in response.headers}


async def test_independent_requests_and_result_meta(http_server: EdiServer) -> None:
    async with AppHarness(http_server) as client:
        results = []
        for i in range(3):
            _, message = await rpc(
                client, "tools/call", {"name": "edi_ping", "arguments": {}}, request_id=100 + i
            )
            results.append(message["result"])
    for result in results:
        assert result["resultType"] == "complete"
        assert result["structuredContent"]["pong"] == "ok"
        assert SERVER_INFO in result["_meta"] and META_UPSTREAM in result["_meta"]
        assert json.loads(result["content"][0]["text"]) == result["structuredContent"]


async def test_header_routing_is_enforced(http_server: EdiServer) -> None:
    async with AppHarness(http_server) as client:
        wrong_name, msg = await rpc(
            client,
            "tools/call",
            {"name": "edi_ping", "arguments": {}},
            headers={"Mcp-Name": "edi_get_metadata"},
        )
        wrong_method = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": LATEST_PROTOCOL_VERSION,
                        "io.modelcontextprotocol/clientCapabilities": {},
                    }
                },
            },
            headers=mcp_headers("prompts/list"),
        )
    assert wrong_name.status_code == 400 and "does not match" in msg["error"]["message"]
    assert wrong_method.status_code == 400


async def test_protocol_version_errors(http_server: EdiServer) -> None:
    """Header/envelope mismatch is -32020; an unsupported version is -32022.

    (SDK 2.2.0 treats an *older* header, e.g. 2025-11-25, as the legacy era and
    serves it, so the mismatch case uses a modern header with another envelope.)
    """
    async with AppHarness(http_server) as client:
        mismatch_resp, mismatch = await rpc(
            client, "tools/list", meta={"io.modelcontextprotocol/protocolVersion": "2030-01-01"}
        )
        unsupported_resp, unsupported = await rpc(
            client,
            "tools/list",
            headers={"MCP-Protocol-Version": "2030-01-01"},
            meta={"io.modelcontextprotocol/protocolVersion": "2030-01-01"},
        )
    assert mismatch_resp.status_code == 400 and mismatch["error"]["code"] == -32020
    assert unsupported_resp.status_code == 400 and unsupported["error"]["code"] == -32022
    assert unsupported["error"]["data"]["supported"] == [LATEST_PROTOCOL_VERSION]


async def test_host_allow_list(make_server: Callable[..., EdiServer], config: Config) -> None:
    cfg = config.model_copy(deep=True)
    cfg.server.public_base_url = "https://edi.example.test"
    server = make_server(transport="http", config=cfg)
    async with AppHarness(server, base_url="http://edi.example.test") as client:
        ok, _ = await rpc(client, "tools/list")
        forged, _ = await rpc(client, "tools/list", headers={"Host": "attacker.example"})
    assert ok.status_code == 200 and forged.status_code == 421


async def test_resources_over_http(http_server: EdiServer) -> None:
    async with AppHarness(http_server) as client:
        _, resources = await rpc(client, "resources/list")
        _, templates = await rpc(client, "resources/templates/list")
        _, read = await rpc(client, "resources/read", {"uri": "edi://guide/api-key"})
        _, missing = await rpc(client, "resources/read", {"uri": "edi://guide/api-kye"})
    for listing in (resources, templates):
        assert listing["result"]["cacheScope"] == "public" and listing["result"]["ttlMs"] > 0
    assert {r["uri"] for r in resources["result"]["resources"]} >= {
        "edi://guide/api-key",
        "edi://guide/package-identifiers",
    }
    assert (
        read["result"]["ttlMs"] == RESOURCE_READ_STATIC_TTL_MS
        and read["result"]["cacheScope"] == "public"
    )
    assert "X-EDI-Key" in read["result"]["contents"][0]["text"]
    assert missing["error"]["code"] == -32602 and missing["error"]["data"]["code"] == "not_found"
    assert "edi://guide/api-key" in missing["error"]["data"]["didYouMean"]


async def test_mrtr_round_trip_over_http(http_server: EdiServer, conformance_tool: None) -> None:
    caps = {"io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}}}}
    async with AppHarness(http_server) as client:
        _, first = await rpc(
            client, "tools/call", {"name": "edi__conformance_elicit", "arguments": {}}, meta=caps
        )
        result = first["result"]
        assert result["resultType"] == "input_required"
        request = result["inputRequests"]["choice"]
        assert request["method"] == "elicitation/create" and request["params"]["mode"] == "form"
        _, second = await rpc(
            client,
            "tools/call",
            {
                "name": "edi__conformance_elicit",
                "arguments": {},
                "inputResponses": {"choice": {"action": "accept", "content": {"choice": "blue"}}},
                "requestState": result["requestState"],
            },
            meta=caps,
        )
        _, tampered = await rpc(
            client,
            "tools/call",
            {
                "name": "edi__conformance_elicit",
                "arguments": {},
                "inputResponses": {"choice": {"action": "accept", "content": {"choice": "blue"}}},
                "requestState": "dGFtcGVyZWQ",
            },
            meta=caps,
        )
        _, no_caps = await rpc(
            client, "tools/call", {"name": "edi__conformance_elicit", "arguments": {}}
        )
    assert second["result"]["structuredContent"]["choice"] == "blue"
    assert tampered["result"]["isError"] is True
    assert tampered["result"]["structuredContent"]["error"]["code"] == "invalid_argument"
    assert no_caps["result"]["structuredContent"]["choice"] == "fallback"


def test_session_manager_is_stateless(http_server: EdiServer) -> None:
    from edi_mcp.transport.streamable_http import build_http_app

    app = build_http_app(http_server)
    manager = app.state.mcp_server.session_manager
    assert manager is not None and manager.stateless is True
