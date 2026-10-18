"""Upstream backends: PASTA with a key, DataONE without (DESIGN.md D1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from edi_mcp.edi.backends.base import (
    Backend,
    BoundingBox,
    EntityInfo,
    ResolvedPackage,
    SearchHit,
    SearchPage,
    SearchQuery,
    resolve_package,
)
from edi_mcp.edi.backends.dataone import DataOneBackend
from edi_mcp.edi.backends.pasta import PastaBackend

if TYPE_CHECKING:
    from edi_mcp.context import ToolContext


def backend_for(ctx: ToolContext) -> PastaBackend | DataOneBackend:
    """The backend serving this call; a key always means PASTA (a bad key is an error, D2)."""
    if ctx.client is None:  # pragma: no cover - every server builds a client
        raise RuntimeError("tool context has no upstream client")
    if ctx.api_key is None:
        return DataOneBackend(ctx.client, ctx.config, ctx.stats)
    pasta = PastaBackend(ctx.client, ctx.config, ctx.stats, ctx.api_key)
    # Built after PASTA so the call's stats keep backend="pasta".
    pasta.set_fallback(DataOneBackend(ctx.client, ctx.config, ctx.stats))
    return pasta


__all__ = [
    "Backend",
    "BoundingBox",
    "DataOneBackend",
    "EntityInfo",
    "PastaBackend",
    "ResolvedPackage",
    "SearchHit",
    "SearchPage",
    "SearchQuery",
    "backend_for",
    "resolve_package",
]
