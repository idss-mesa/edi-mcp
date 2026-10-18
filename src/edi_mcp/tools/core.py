"""``edi_ping``: liveness and capability report."""

from __future__ import annotations

from typing import Literal

from mcp.types import LATEST_PROTOCOL_VERSION
from pydantic import Field

from edi_mcp import __version__
from edi_mcp.context import ToolContext
from edi_mcp.errors import KEY_PAGE_URL
from edi_mcp.models.common import EdiInput, EdiOutput, Source, ToolResultBase
from edi_mcp.registry import get_registered_tools, register_tool


class PingIn(EdiInput):
    """``edi_ping`` takes no arguments; it never calls upstream."""


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


@register_tool(
    "edi_ping",
    title="Check edi-mcp status",
    description=(
        "Liveness and capability report: server version and protocol, whether an EDI API key is "
        "available and therefore which backend serves this caller (pasta with a key, dataone "
        "without), which tools need a key, and whether downloads are enabled. Makes no upstream "
        "request and never reveals the key. Next: call edi_search_packages to find data packages."
    ),
    input_model=PingIn,
    output_model=PingResult,
    surface="core",
    endpoints=[],
)
async def edi_ping(args: PingIn, ctx: ToolContext) -> PingResult:
    del args
    cfg = ctx.config
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
        notes=notes,
        next_steps=steps,
        source=Source(endpoints=[], backend="local", cached=False),
    )
