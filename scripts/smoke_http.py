"""Smoke-test a running edi-mcp HTTP server (stdlib only, so it runs inside the image).

    docker exec -i <container> python - [--offline] < scripts/smoke_http.py
    python scripts/smoke_http.py [--offline] http://127.0.0.1:8080

Checks /healthz and /readyz, tools/list, prompts/list, the resource templates, one
static resource and (unless ``--offline``) one anonymous search, which reaches DataONE.
Exits non-zero on the first failure.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any

ARGS = [a for a in sys.argv[1:] if a != "-"]
OFFLINE = "--offline" in ARGS
BASE = next((a for a in ARGS if not a.startswith("--")), "http://127.0.0.1:8080").rstrip("/")
PV = "2026-07-28"
if not BASE.startswith(("http://", "https://")):
    raise SystemExit(f"not an http(s) URL: {BASE}")


def get(path: str) -> dict[str, Any]:
    with urllib.request.urlopen(BASE + path, timeout=30) as response:  # noqa: S310
        return json.loads(response.read())  # type: ignore[no-any-return]


def call(method: str, params: dict[str, Any] | None = None, name: str | None = None) -> Any:
    meta = {
        "io.modelcontextprotocol/protocolVersion": PV,
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": {**(params or {}), "_meta": meta},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PV,
        "Mcp-Method": method,
    }
    if name:
        headers["Mcp-Name"] = name
    request = urllib.request.Request(BASE + "/mcp", json.dumps(body).encode(), headers)  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        raw = response.read().decode()
    lines = [line[5:] for line in raw.splitlines() if line.startswith("data:")]
    message = json.loads(lines[0] if lines else raw)
    if "error" in message:
        raise SystemExit(f"{method}: {message['error']}")
    return message["result"]


def main() -> None:
    assert get("/healthz")["status"] == "ok"
    assert get("/readyz")["status"] == "ready"
    tools = [t["name"] for t in call("tools/list")["tools"]]
    assert "edi_search_packages" in tools and "edi_download_entities" not in tools, tools
    prompts = {p["name"] for p in call("prompts/list")["prompts"]}
    assert prompts == {"edi_cite_package", "edi_find_data", "edi_plan_download"}, prompts
    templates = call("resources/templates/list")["resourceTemplates"]
    assert {t["uriTemplate"] for t in templates} == {
        "edi://packages/{packageId}",
        "edi://packages/{packageId}/eml",
    }
    uri = "edi://guide/agent-workflow"
    guide = call("resources/read", {"uri": uri}, uri)
    assert "edi_search_packages" in guide["contents"][0]["text"]
    if OFFLINE:
        print(f"ok: {len(tools)} tools, {len(prompts)} prompts (offline)")
        return
    args = {"query": "streamflow", "scope": "HBR", "limit": 2}
    result = call(
        "tools/call", {"name": "edi_search_packages", "arguments": args}, "edi_search_packages"
    )
    assert not result.get("isError"), result
    found = result["structuredContent"]
    print(f"ok: {len(tools)} tools, backend {found['source']['backend']}, page {found['page']}")


if __name__ == "__main__":
    main()
