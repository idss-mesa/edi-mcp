"""EDI API key model, per-call resolution and the HTTP TLS gate.

Since 2026-07-30 PASTA requires credentials for every endpoint. edi-mcp reads
an EDI API access key (DESIGN.md D5) and, with one, serves from PASTA;
without one it serves from DataONE (D1). The key is exchanged for a
short-lived ``edi-token`` by the client (D4). An :class:`ApiKey` never prints
its value, and every key the process sees is registered with the log
redactor.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import structlog

from edi_mcp.errors import auth_required_error
from edi_mcp.logging import register_secret

if TYPE_CHECKING:
    from edi_mcp.config import Config
    from edi_mcp.context import ToolContext

log = structlog.get_logger("edi_mcp.auth")

_warned_insecure_header = False


@dataclass(frozen=True, repr=False)
class ApiKey:
    """An EDI API access key. ``repr``/``str`` never reveal the value."""

    value: str = field(repr=False)
    source: Literal["config", "request"]

    def __post_init__(self) -> None:
        register_secret(self.value)

    def identity(self) -> str:
        """Stable non-reversible key for caches and token slots."""
        return "key:" + hashlib.sha256(self.value.encode("utf-8")).hexdigest()[:12]

    def __repr__(self) -> str:
        return f"ApiKey(<redacted>, source={self.source!r})"

    __str__ = __repr__


def header_key_allowed(config: Config) -> bool:
    """Per-request header keys need TLS in front (or an explicit dev override)."""
    base = config.server.public_base_url or ""
    return base.lower().startswith("https://") or config.server.allow_insecure_header_key


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def resolve_key(
    config: Config,
    *,
    transport: Literal["stdio", "http"],
    request_headers: Mapping[str, str] | None,
) -> ApiKey | None:
    """Pick the API key for one call (DESIGN.md D6).

    stdio: the configured key. http: the caller's header key when accepted and
    the TLS gate allows it; else the configured key only when the operator
    opted into sharing it; else ``None``. The MCP-level ``Authorization``
    header is never read here and never forwarded upstream.
    """
    global _warned_insecure_header
    configured = config.key_value()
    if transport == "stdio":
        return ApiKey(configured, "config") if configured else None

    if request_headers and config.server.accept_header_key:
        raw = _header(request_headers, config.server.request_key_header)
        value = raw.strip() if raw else ""
        if value:
            if header_key_allowed(config):
                return ApiKey(value, "request")
            if not _warned_insecure_header:
                _warned_insecure_header = True
                log.warning(
                    "auth.header_key_ignored",
                    reason="public_base_url is not https:// and allow_insecure_header_key is false",
                )
    if configured and config.server.share_config_key_over_http:
        return ApiKey(configured, "config")
    return None


def require_key(ctx: ToolContext, *, endpoint: str | None = None) -> ApiKey:
    """Return the call's key or fail with ``auth_required`` before any request."""
    if ctx.api_key is None:
        raise auth_required_error(tool=ctx.tool_name, endpoint=endpoint)
    return ctx.api_key


def _reset_warning_for_tests() -> None:
    global _warned_insecure_header
    _warned_insecure_header = False


__all__ = ["ApiKey", "header_key_allowed", "require_key", "resolve_key"]
