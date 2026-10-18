"""Per-call context handed to every tool handler.

Handlers take ``(args, ctx)``. :class:`ToolContext` carries the process-wide
config, the call's resolved EDI API key (never logged), which backend serves
the call (``pasta`` with a key, ``dataone`` without; DESIGN.md D1), the
caller's MRTR capability, and an :class:`UpstreamStats` accumulator that feeds
the ``io.edi-mcp/upstream`` result ``_meta``.

HTTP-scoped values (request headers, request id) reach the MCP adapter
through the context variables below, set by
:class:`edi_mcp.transport.streamable_http.RequestContextMiddleware`.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import structlog

if TYPE_CHECKING:
    from edi_mcp.config import Config
    from edi_mcp.edi.auth import ApiKey
    from edi_mcp.edi.client import EdiClient

TransportName = Literal["stdio", "http"]
BackendName = Literal["pasta", "dataone"]

current_transport: ContextVar[TransportName | None] = ContextVar("edi_mcp_transport", default=None)
current_request_headers: ContextVar[Mapping[str, str] | None] = ContextVar(
    "edi_mcp_request_headers", default=None
)
current_request_id: ContextVar[str | None] = ContextVar("edi_mcp_request_id", default=None)


@dataclass
class UpstreamStats:
    """What one tool call cost upstream (reported in result ``_meta``)."""

    requests: int = 0
    cache_hits: int = 0
    backend: BackendName | None = None
    credential: Literal["none", "token", "key"] = "none"
    endpoints: list[str] = field(default_factory=list)

    def record_endpoint(self, endpoint: str) -> None:
        if endpoint not in self.endpoints:
            self.endpoints.append(endpoint)

    def as_meta(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "cacheHits": self.cache_hits,
            "backend": self.backend,
            "credential": self.credential,
        }


@dataclass(frozen=True)
class Elicited:
    """An MRTR follow-up: the user's answers plus the decoded continuation."""

    responses: Mapping[str, Any]
    state: Mapping[str, Any]


@dataclass(frozen=True)
class ToolContext:
    config: Config
    transport: TransportName
    tool_name: str
    api_key: ApiKey | None
    client_capabilities: Mapping[str, Any]
    elicitation_supported: bool
    elicited: Elicited | None
    request_id: str | None
    stats: UpstreamStats
    log: Any
    #: The process-wide upstream client (``None`` only in bare unit tests).
    client: EdiClient | None = None

    @property
    def key_source(self) -> Literal["config", "request", "none"]:
        return self.api_key.source if self.api_key is not None else "none"

    @property
    def backend(self) -> BackendName:
        """``pasta`` when this call has a key, else ``dataone`` (DESIGN.md D1)."""
        return "pasta" if self.api_key is not None else "dataone"


def build_tool_context(
    *,
    config: Config,
    transport: TransportName,
    tool_name: str,
    client_capabilities: Mapping[str, Any] | None = None,
    elicited: Elicited | None = None,
    request_id: str | None = None,
    request_headers: Mapping[str, str] | None = None,
    stats: UpstreamStats | None = None,
    client: EdiClient | None = None,
) -> ToolContext:
    """Resolve the call's API key and assemble a :class:`ToolContext`."""
    from edi_mcp.edi.auth import resolve_key

    caps = dict(client_capabilities or {})
    api_key = resolve_key(config, transport=transport, request_headers=request_headers)
    return ToolContext(
        config=config,
        transport=transport,
        tool_name=tool_name,
        api_key=api_key,
        client_capabilities=caps,
        elicitation_supported="elicitation" in caps,
        elicited=elicited,
        request_id=request_id,
        stats=stats if stats is not None else UpstreamStats(),
        log=structlog.get_logger("edi_mcp.tool").bind(tool=tool_name, request_id=request_id),
        client=client,
    )
