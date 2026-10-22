---
title: "Transports"
description: "The stdio and stateless Streamable HTTP transports: routes, health checks, header routing, DNS-rebinding protection and per-request EDI API keys."
type: Reference
tags:
  - mcp
  - transports
  - http
  - stdio
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: mcp-transports
    resource: "https://modelcontextprotocol.io/specification/2026-07-28/basic/transports"
    title: "MCP specification — Transports"
    author: "team:modelcontextprotocol"
status: stable
---

# Transports

## stdio (default)

`edi-mcp` (or `edi-mcp --transport stdio`) serves one client over standard input and
output, the usual setup for Claude Code, Claude Desktop and other local clients. Only
MCP framing goes to stdout; logs go to stderr. The key in the server's environment
(`EDI_API_KEY`) is used for every call, and the stdio-only download tools are
offered only here. The SDK's stdio loop serves both protocol eras: a
client that starts with the legacy `initialize` handshake and a 2026-07-28 client
both work.

## Streamable HTTP (stateless)

`edi-mcp --transport http` serves on `127.0.0.1:8080` by default (`--bind-address`,
`--bind-port`)[^mcp-transports]:

| Route | Behaviour |
| --- | --- |
| `POST /mcp` (and `/mcp/`) | JSON-RPC over Streamable HTTP; one response per request (a single SSE frame, or JSON with `server.json_response`). |
| `GET /mcp`, `DELETE /mcp` | 405 with `Allow: POST`: the server sends no server-initiated messages and keeps no sessions. |
| `GET /healthz` | Liveness, always 200 while the process serves: `{"status": "ok", "version", "protocolVersion", "transport"}`. |
| `GET /readyz` | Readiness: 503 `{"status": "warming"}` during startup work, then 200 `{"status": "ready", "degraded", "keyConfigured"}`. It never reveals the key. |

The server runs stateless: there is no `Mcp-Session-Id`, and any instance can answer
any request, so it scales horizontally behind a load balancer. Every response carries
`X-Request-Id` (yours, if you sent a well-formed one). Request bodies are capped at
1 MiB (`server.max_request_body_size`).

### Header checks

For 2026-07-28 requests the SDK checks the HTTP headers against the JSON-RPC body:

* `Mcp-Method` must match the body's `method`, and `Mcp-Name` the tool name,
  resource URI or prompt name; a mismatch is HTTP 400.
* `MCP-Protocol-Version` must agree with the version in the request's `_meta`
  envelope (`-32020` otherwise); an unsupported version is `-32022`, with the
  supported versions in `error.data.supported`.

A request whose `MCP-Protocol-Version` header names an older revision is served in
the legacy era, still without a session.

### Host and origin checks

DNS-rebinding protection is on automatically for loopback binds. For a public
deployment set `server.public_base_url` (its host and origin join the allow-lists)
and optionally `server.allowed_hosts` / `server.allowed_origins`; a request with any
other `Host` gets 421. Behind a proxy that rewrites `Host`, set
`server.dns_rebinding_protection = false`.

### Per-request EDI API keys

Each HTTP caller sends its own EDI API key in the `X-EDI-Key` header (configurable
with `server.request_key_header`; turn it off with `server.accept_header_key =
false`). The header is honoured only when `server.public_base_url` starts with
`https://`, meaning TLS terminates in front of the server, or when
`server.allow_insecure_header_key` is set for development. Otherwise the header is
stripped before any handler sees it and one warning is logged.

A caller without a key is served from DataONE: the operator's configured key is not
lent to HTTP callers unless `server.share_config_key_over_http` is set, which is meant
for private deployments only. The MCP-level `Authorization` header is never forwarded
to EDI. Download tools are never offered over HTTP.

[^mcp-transports]: MCP specification — Transports. <https://modelcontextprotocol.io/specification/2026-07-28/basic/transports>
