---
title: "Hosted HTTP deployment"
description: "Run edi-mcp as a stateless Streamable HTTP service behind a TLS reverse proxy: binding, public_base_url, host allow-lists, per-caller EDI API keys and health endpoints."
type: Guide
tags:
  - deploy
  - http
  - reverse-proxy
  - systemd
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: mcp-transports
    resource: "https://modelcontextprotocol.io/specification/2026-07-28/basic/transports"
    title: "MCP 2026-07-28 — Transports"
    author: "team:modelcontextprotocol"
  - id: uvicorn
    resource: "https://www.uvicorn.org/deployment/"
    title: "Uvicorn — Deployment"
    author: "team:encode"
  - id: caddy
    resource: "https://caddyserver.com/docs/caddyfile/directives/reverse_proxy"
    title: "Caddy — reverse_proxy"
    author: "team:caddy"
status: stable
---

# Hosted HTTP deployment

A hosted edi-mcp lets many users connect with
`claude mcp add --transport http edi https://edi-mcp.example.org/mcp`. The HTTP
transport is stateless Streamable HTTP[^mcp-transports] at `/mcp`: no session
header, no server-initiated stream, so any instance can answer any request and
instances can sit behind a plain load balancer.

```bash
edi-mcp --transport http --bind-address 127.0.0.1 --bind-port 8080
```

`POST /mcp` takes JSON-RPC requests; `GET` and `DELETE` on `/mcp` return 405
with `Allow: POST`. `/mcp/` is served directly rather than redirected. Every
response carries an `x-request-id` header (the caller's own value when it is a
short safe token, otherwise a generated one) that also appears in the JSON logs.

## Configuration essentials

```bash
EDI_MCP_SERVER__TRANSPORT=http
EDI_MCP_SERVER__BIND_ADDRESS=127.0.0.1          # the proxy connects locally
EDI_MCP_SERVER__BIND_PORT=8080
EDI_MCP_SERVER__PUBLIC_BASE_URL=https://edi-mcp.example.org
```

`public_base_url` does two things:

* its host and origin join the `Host` and `Origin` allow-lists
  (`server.allowed_hosts`, `server.allowed_origins`) used for DNS-rebinding
  protection. Add any other names the service answers on to those lists;
  `server.dns_rebinding_protection` forces the check on or off (unset leaves
  the SDK default, which is on for loopback binds or when allow-lists are set);
* when it starts with `https://`, it opens the TLS gate for per-caller keys
  (below).

Other HTTP settings: `server.json_response` answers `POST /mcp` with
`application/json` instead of a single SSE frame, and
`server.max_request_body_size` (default 1 MiB) caps request bodies. All settings
are listed on the [Configuration](../getting-started/configuration.md) page.

## EDI API keys over HTTP

Each caller brings their own EDI API key in the `X-EDI-Key` header (the name is
`server.request_key_header`). The header is honoured only when
`public_base_url` is `https://`; otherwise the middleware strips it before any
handler sees it and logs one warning. `server.allow_insecure_header_key`
overrides the gate for local development only.

A call with a key is served by PASTA; a call without one is served anonymously
from DataONE, as on stdio (see [Backends](../tools/backends.md)). The
operator's own key (`EDI_API_KEY` in the server's environment) is **not** lent
to HTTP callers unless `server.share_config_key_over_http` is true; enable that
only on a private deployment where every caller may act as the operator. The
MCP-level `Authorization` header is never forwarded to EDI. See
[Security](security.md) for the full key-handling rules.

## Behind a reverse proxy

Terminate TLS at the proxy (the key is a bearer secret), forward `Host`
unchanged, and pass `X-EDI-Key` through. uvicorn runs with proxy headers
enabled[^uvicorn]. Caddy[^caddy]:

```text
edi-mcp.example.org {
    reverse_proxy 127.0.0.1:8080
}
```

nginx:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
    proxy_buffering off;          # single SSE frame per response
}
```

## systemd

```ini
[Unit]
Description=edi-mcp (Streamable HTTP)
After=network-online.target

[Service]
User=edi
EnvironmentFile=/etc/edi-mcp.env
ExecStart=/opt/edi-mcp/.venv/bin/edi-mcp --transport http
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
```

Keep `/etc/edi-mcp.env` readable by the service user only if it holds an
operator key.

## Container image

The repository's `Dockerfile` builds a `python:3.13-slim` image that installs
edi-mcp into `/app/.venv`, runs it as user `edi` (uid 10001) with
`--transport http --bind-address 0.0.0.0` on port 8080, and checks `/healthz` every
30 seconds. Nothing is written to disk, so it runs on a read-only root file system:

```bash
docker build -t edi-mcp .
docker run -d --name edi-mcp --read-only --tmpfs /tmp \
  -p 127.0.0.1:8080:8080 \
  -e EDI_MCP_SERVER__PUBLIC_BASE_URL=https://edi-mcp.example.org \
  -e EDI_MCP_SERVER__ALLOWED_HOSTS=edi-mcp.example.org \
  edi-mcp
```

`docker-compose.yml` does the same, reading `PUBLIC_BASE_URL` and `ALLOWED_HOSTS` from
the environment (empty values count as unset). Publish the port on `127.0.0.1` only and
put the TLS proxy in front: callers' `X-EDI-Key` headers are secrets. To lend an
operator key to every caller, pass `EDI_API_KEY` from the host environment
(`-e EDI_API_KEY`, never the value on the command line) and set
`EDI_MCP_SERVER__SHARE_CONFIG_KEY_OVER_HTTP=true`. `scripts/smoke_http.py` checks a
running instance (`docker exec -i edi-mcp python - --offline < scripts/smoke_http.py`),
as CI does for every change.

## Health and readiness

* `GET /healthz` is liveness only: always 200 with `status`, `version`,
  `protocolVersion` and `transport`; it contacts nothing upstream.
* `GET /readyz` returns 503 with `status: warming` while startup work runs, then
  200 with `status: ready`, `degraded` and `keyConfigured` (whether an operator
  key is set; the key itself is never shown).

## Not available over HTTP

Downloads exist only on stdio, confined to `downloads.directory`: the
download tools (`edi_download_entities`, `edi_download_package`) are never listed over HTTP. Each instance keeps its own
in-memory response cache (`cache.*` settings), so instances do not share state.

[^mcp-transports]: MCP 2026-07-28 — Transports. <https://modelcontextprotocol.io/specification/2026-07-28/basic/transports>
[^uvicorn]: Uvicorn — Deployment. <https://www.uvicorn.org/deployment/>
[^caddy]: Caddy — reverse_proxy. <https://caddyserver.com/docs/caddyfile/directives/reverse_proxy>
