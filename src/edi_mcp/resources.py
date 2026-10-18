"""MCP resources: static guides (derived references and templates arrive with the backends)."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from mcp import types as t

from edi_mcp.errors import ToolError

if TYPE_CHECKING:
    from edi_mcp.context import ToolContext

STATIC_DIR = Path(__file__).parent / "resources_static"
META_RESOURCE_KIND = "io.edi-mcp/kind"
STATIC_TTL_MS = 86_400_000
DERIVED_TTL_MS = 3_600_000


@dataclass(frozen=True)
class ResourceContent:
    text: str
    mime_type: str
    ttl_ms: int
    kind: Literal["static", "derived"]


@dataclass(frozen=True)
class _Static:
    uri: str
    file: str
    mime_type: str
    title: str
    description: str


STATIC: tuple[_Static, ...] = (
    _Static(
        "edi://guide/api-key",
        "api-key.md",
        "text/markdown",
        "EDI API key",
        "Why EDI needs a key since 2026-07-30, how to create one, how edi-mcp uses it, and what "
        "works without one.",
    ),
    _Static(
        "edi://guide/package-identifiers",
        "package-identifiers.md",
        "text/markdown",
        "Package identifiers",
        "Scopes, scope.identifier.revision, newest/oldest, DOIs, entity ids and the forms "
        "edi-mcp accepts.",
    ),
)


def list_resources() -> list[t.Resource]:
    out = [
        t.Resource(
            name=s.uri.rsplit("/", 1)[-1],
            uri=s.uri,
            title=s.title,
            description=s.description,
            mime_type=s.mime_type,
            meta={META_RESOURCE_KIND: "static"},
        )
        for s in STATIC
    ]
    return sorted(out, key=lambda r: str(r.uri))


def list_resource_templates() -> list[t.ResourceTemplate]:
    return []


@lru_cache(maxsize=16)
def _static_text(file: str) -> str:
    return (STATIC_DIR / file).read_text(encoding="utf-8")


def known_uris() -> list[str]:
    return [s.uri for s in STATIC]


async def read_resource(uri: str, ctx: ToolContext, *, server: Any = None) -> ResourceContent:
    """Read one ``edi://`` resource; ``ToolError(not_found)`` with ``didYouMean`` otherwise."""
    del ctx, server
    for s in STATIC:
        if s.uri == uri:
            return ResourceContent(_static_text(s.file), s.mime_type, STATIC_TTL_MS, "static")
    raise ToolError(
        "not_found",
        f"Unknown resource {uri!r}.",
        details={
            "uri": uri,
            "didYouMean": difflib.get_close_matches(uri, known_uris(), n=3, cutoff=0.4),
        },
    )
