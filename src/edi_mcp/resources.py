"""MCP resources: static guides, the scope snapshot, and package templates (D21).

Static guides are the same for everyone (``cacheScope: public``). Template reads
depend on the caller: a key reaches PASTA (current, and restricted packages the
key may read) while anonymous reads come from DataONE, which can lag, so they are
``private``.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import unquote

from mcp import types as t
from pydantic import ValidationError

from edi_mcp.errors import EdiApiError, ToolError, map_api_error
from edi_mcp.logging import registered_secrets

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
    cache_scope: Literal["public", "private"] = "public"


@dataclass(frozen=True)
class _Static:
    uri: str
    file: str
    mime_type: str
    title: str
    description: str


@dataclass(frozen=True)
class _Template:
    uri_template: str
    pattern: re.Pattern[str]
    name: str
    mime_type: str
    title: str
    description: str


STATIC: tuple[_Static, ...] = (
    _Static(
        "edi://guide/agent-workflow",
        "agent-workflow.md",
        "text/markdown",
        "Agent workflow",
        "Five-call recipe from a question to cited data, input forms, keys and error remedies.",
    ),
    _Static(
        "edi://guide/api-key",
        "api-key.md",
        "text/markdown",
        "EDI API key",
        "Why EDI needs a key since 2026-07-30, how to create one, how edi-mcp uses it, and what "
        "works without one.",
    ),
    _Static(
        "edi://guide/citing-edi-data",
        "citing-edi-data.md",
        "text/markdown",
        "Citing EDI data",
        "Cite one revision by its DOI: citation styles, rights and EDI's data policy.",
    ),
    _Static(
        "edi://guide/package-identifiers",
        "package-identifiers.md",
        "text/markdown",
        "Package identifiers",
        "Scopes, scope.identifier.revision, newest/oldest, DOIs, entity ids and the forms "
        "edi-mcp accepts.",
    ),
    _Static(
        "edi://guide/search-syntax",
        "search-syntax.md",
        "text/markdown",
        "Search syntax",
        "Query text (words are ORed; phrases, AND/OR/NOT), filters and PASTA vs DataONE "
        "differences for edi_search_packages.",
    ),
    _Static(
        "edi://reference/scopes",
        "scopes.json",
        "application/json",
        "EDI scopes",
        "Every scope with name, kind, LTER site code, location and package counts on PASTA and "
        "DataONE (dated snapshot); scope arguments accept these site codes and names.",
    ),
)


_PACKAGE = r"([^/?#]+)"
TEMPLATES: tuple[_Template, ...] = (
    _Template(
        "edi://packages/{packageId}",
        re.compile(rf"^edi://packages/{_PACKAGE}$"),
        "package",
        "application/json",
        "EDI data package",
        "A package's summary (the edi_get_package payload). packageId is scope.identifier"
        "[.revision], e.g. knb-lter-hbr.14.22; without a revision, the newest.",
    ),
    _Template(
        "edi://packages/{packageId}/eml",
        re.compile(rf"^edi://packages/{_PACKAGE}/eml$"),
        "package-eml",
        "application/xml",
        "EDI package EML",
        "The package's raw EML metadata document (XML). Usually large: prefer "
        "edi_get_metadata, which returns a compact projection.",
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
    return [
        t.ResourceTemplate(
            name=tpl.name,
            uri_template=tpl.uri_template,
            title=tpl.title,
            description=tpl.description,
            mime_type=tpl.mime_type,
        )
        for tpl in TEMPLATES
    ]


@lru_cache(maxsize=16)
def _static_text(file: str) -> str:
    return (STATIC_DIR / file).read_text(encoding="utf-8")


def known_uris() -> list[str]:
    return [s.uri for s in STATIC] + [tpl.uri_template for tpl in TEMPLATES]


def _compact(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


async def _package_summary(package: str, ctx: ToolContext) -> str:
    from edi_mcp.registry import get_tool, invoke

    return _compact(await invoke(get_tool("edi_get_package"), {"package": package}, ctx))


async def _raw_eml(package: str, ctx: ToolContext) -> str:
    from edi_mcp.edi.backends import backend_for, resolve_package
    from edi_mcp.tools.data import require_replicated
    from edi_mcp.tools.packages import PackageArgs

    try:
        args = PackageArgs(package=package)
    except ValidationError:
        raise ToolError(
            "invalid_argument", f"Not a package identifier: {package[:100]!r}."
        ) from None
    require_replicated(args, ctx)
    backend = backend_for(ctx)
    try:
        resolved = await resolve_package(backend, args.package, args.revision)
        body = await backend.read_eml(resolved.package)
    except EdiApiError as exc:
        raise map_api_error(exc, secrets=registered_secrets()) from None
    limit = ctx.config.limits.max_resource_bytes
    if len(body) > limit:
        raise ToolError(
            "result_too_large",
            f"The EML of {resolved.package.package_id} is {len(body)} bytes, above the "
            f"{limit}-byte resource limit.",
            details={"bytes": len(body), "limit": limit},
            hint="Call edi_get_metadata for a compact projection of it.",
        )
    return body.decode("utf-8", errors="replace")


async def read_resource(uri: str, ctx: ToolContext, *, server: Any = None) -> ResourceContent:
    """Read one ``edi://`` resource; ``ToolError(not_found)`` with ``didYouMean`` otherwise."""
    del server
    for s in STATIC:
        if s.uri == uri:
            return ResourceContent(_static_text(s.file), s.mime_type, STATIC_TTL_MS, "static")
    for tpl in TEMPLATES:
        match = tpl.pattern.match(uri)
        if match is None:
            continue
        package = unquote(match.group(1))
        text = (
            await _raw_eml(package, ctx)
            if tpl.name == "package-eml"
            else await _package_summary(package, ctx)
        )
        return ResourceContent(text, tpl.mime_type, DERIVED_TTL_MS, "derived", "private")
    raise ToolError(
        "not_found",
        f"Unknown resource {uri!r}.",
        details={
            "uri": uri,
            "didYouMean": difflib.get_close_matches(uri, known_uris(), n=3, cutoff=0.4),
        },
    )
