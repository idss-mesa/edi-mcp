"""``edi_ping``: liveness and capability report."""

from __future__ import annotations

import time
from typing import Any, Literal

from mcp.types import LATEST_PROTOCOL_VERSION
from pydantic import Field

from edi_mcp import __version__
from edi_mcp.context import ToolContext
from edi_mcp.edi.backends.dataone import SOURCE_FILTER
from edi_mcp.errors import KEY_PAGE_URL, EdiApiError, ToolError, map_api_error
from edi_mcp.logging import registered_secrets
from edi_mcp.models.common import EdiInput, EdiOutput, Source, ToolResultBase
from edi_mcp.registry import get_registered_tools, register_tool


class PingIn(EdiInput):
    """``edi_ping`` arguments."""

    check_api: bool = Field(
        False,
        description="Also make one small request to the backend serving this caller (with a "
        "key: exchange it for a token and list PASTA scopes; without: one DataONE query).",
    )


class ApiCheck(EdiOutput):
    reachable: bool = Field(description="True when the backend answered the check request.")
    backend: Literal["pasta", "dataone"]
    credential: Literal["none", "token", "key"] = Field(
        description="How the request was authenticated: an edi-token cookie, the key as a query "
        "parameter (auth service unavailable), or none (DataONE)."
    )
    endpoint: str
    latency_ms: float
    error: dict[str, Any] | None = Field(
        None, description="The error code and message when the check failed."
    )


class Endpoints(EdiOutput):
    pasta: str
    auth: str
    dataone_cn: str
    cite: str


class PingResult(ToolResultBase):
    pong: Literal["ok"] = "ok"
    version: str
    protocol_version: str
    transport: Literal["stdio", "http"]
    key_configured: bool = Field(
        description="True when this call has an EDI API key available (never the key itself)."
    )
    key_source: Literal["config", "request", "none"]
    backend: Literal["pasta", "dataone"] = Field(
        description="Backend serving this caller: pasta with a key, dataone without one."
    )
    key_required_tools: list[str] = Field(
        description="Registered tools that need a key and fail with auth_required without one."
    )
    downloads_enabled: bool
    download_dir: str | None = None
    endpoints: Endpoints
    api: ApiCheck | None = Field(None, description="Present when check_api was requested.")


async def _check_api(ctx: ToolContext) -> ApiCheck:
    if ctx.client is None:  # pragma: no cover - every server builds a client
        raise ToolError("internal_error", "No upstream client is configured.")
    edi = ctx.config.edi
    started = time.monotonic()
    if ctx.api_key is not None:
        url, params = f"{edi.pasta_base_url.rstrip('/')}/package/eml", None
    else:
        url = f"{edi.dataone_cn_url.rstrip('/')}/query/solr/"
        params = {"q": "*:*", "fq": SOURCE_FILTER, "rows": "0", "wt": "json"}
    error: dict[str, Any] | None = None
    credential: Literal["none", "token", "key"] = "none"
    try:
        fetched = await ctx.client.get(url, params, key=ctx.api_key, stats=ctx.stats)
        credential = fetched.credential
    except EdiApiError as exc:
        err = map_api_error(exc, secrets=registered_secrets())
        error = {"code": err.code, "message": err.message}
    except ToolError as err:
        error = {"code": err.code, "message": err.message}
    ctx.stats.backend = ctx.backend
    return ApiCheck(
        reachable=error is None,
        backend=ctx.backend,
        credential=credential,
        endpoint=ctx.stats.endpoints[-1] if ctx.stats.endpoints else url,
        latency_ms=round((time.monotonic() - started) * 1000, 1),
        error=error,
    )


@register_tool(
    "edi_ping",
    title="Check edi-mcp status",
    description=(
        "Liveness and capability report: server version and protocol, whether an EDI API key is "
        "available and therefore which backend serves this caller (pasta with a key, dataone "
        "without), which tools need a key, and whether downloads are enabled. Never reveals the "
        "key. With check_api=true it also makes one small request to that backend to confirm "
        "the key and connectivity. Next: call edi_search_packages to find data packages."
    ),
    input_model=PingIn,
    output_model=PingResult,
    surface="core",
    endpoints=["GET pasta.lternet.edu/package/eml", "GET cn.dataone.org/cn/v2/query/solr/"],
)
async def edi_ping(args: PingIn, ctx: ToolContext) -> PingResult:
    cfg = ctx.config
    api = await _check_api(ctx) if args.check_api else None
    downloads = cfg.effective_downloads_enabled(ctx.transport)
    key_tools = sorted(
        s.name
        for s in get_registered_tools(transport=ctx.transport, downloads_enabled=downloads)
        if s.requires_key
    )
    notes: list[str] = []
    steps = ["edi_search_packages(query='streamflow') to find data packages"]
    if ctx.api_key is None:
        notes.append(
            "No EDI API key: since 2026-07-30 EDI's PASTA API requires one, so edi-mcp serves "
            "search, metadata, entities and citations from DataONE replicas (which can lag new "
            "uploads); quality reports, lineage, change feeds and read counts need a key."
        )
        steps.append(
            f"Read edi://guide/api-key to create a key at {KEY_PAGE_URL} and set EDI_API_KEY"
        )
    return PingResult(
        version=__version__,
        protocol_version=LATEST_PROTOCOL_VERSION,
        transport=ctx.transport,
        key_configured=ctx.api_key is not None,
        key_source=ctx.key_source,
        backend=ctx.backend,
        key_required_tools=key_tools,
        downloads_enabled=downloads,
        download_dir=str(cfg.downloads.directory) if downloads else None,
        endpoints=Endpoints(
            pasta=cfg.edi.pasta_base_url,
            auth=cfg.edi.auth_base_url,
            dataone_cn=cfg.edi.dataone_cn_url,
            cite=cfg.edi.cite_url,
        ),
        api=api,
        notes=notes,
        next_steps=steps,
        source=Source(
            endpoints=list(ctx.stats.endpoints),
            backend=ctx.backend if api is not None else "local",
            cached=False,
        ),
    )
