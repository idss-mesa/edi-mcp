"""Shared test helpers: calling tools and validating their results."""

from __future__ import annotations

import json
from typing import Any

import jsonschema

from edi_mcp.registry import get_tool
from edi_mcp.server import EdiServer
from tests.fixture_router import TEST_KEY

__all__ = ["TEST_KEY", "call_err", "call_ok", "output_schema"]


def output_schema(name: str) -> dict[str, Any]:
    return EdiServer.output_schema(get_tool(name))


async def call_ok(
    server: EdiServer, name: str, args: dict[str, Any] | None = None, **kw: Any
) -> dict[str, Any]:
    """Call a tool, assert success, and validate the payload against its outputSchema."""
    outcome = await server.call(name, args or {}, **kw)
    assert outcome.input_required is None, "unexpected input_required"
    assert not outcome.is_error, json.dumps(outcome.payload, indent=1)[:3000]
    jsonschema.Draft202012Validator(output_schema(name)).validate(outcome.payload)
    return outcome.payload


async def call_err(
    server: EdiServer, name: str, args: dict[str, Any] | None, code: str, **kw: Any
) -> dict[str, Any]:
    """Call a tool, assert it failed with ``code``; return the error object."""
    outcome = await server.call(name, args or {}, **kw)
    assert outcome.is_error, json.dumps(outcome.payload)[:2000]
    error: dict[str, Any] = outcome.payload["error"]
    assert error["code"] == code, error
    return error
