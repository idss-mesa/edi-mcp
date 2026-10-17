# CLAUDE.md — edi-mcp

edi-mcp is a Model Context Protocol server (MCP **2026-07-28**, stateless core) for the
Environmental Data Initiative (EDI) PASTA+ repository, published at
https://github.com/idss-mesa/edi-mcp. Python 3.11+, `mcp>=2.0,<3` (low-level `Server`),
pydantic v2, httpx, structlog, defusedxml. It is a sibling of `idss-mesa/neon-mcp` and
copies its architecture (registry, server adapter, envelope, transports, tests).
`DESIGN.md` records every decision (the D-numbers) and `RESEARCH.md` the verified API
facts; read them before changing behaviour.

## Status

Scaffold. Build order (one PR each): 1 scaffold + auth probe → 2 core port from neon-mcp
→ 3 client/auth/PID resolver/backends + fixtures → 4 discovery tools → 5 package,
metadata and entity tools → 6 preview/download/citation/PASTA-only tools → 7 resources,
prompts, docs, server.json, Docker, v0.1.0.

## Commands

```bash
uv sync --all-extras
uv run pytest                                   # hermetic unit + conformance tests
uv run ruff check src tests scripts && uv run ruff format --check src tests
uv run mypy --strict src
set -a; . ./.env; set +a; python3 scripts/probe_auth.py --json probe.json   # Step 1
```

## Fixed decisions (do not re-litigate)

- Tool prefix `edi_`; inputs snake_case; outputs camelCase.
- Hybrid backend: PASTA when `EDI_API_KEY` is set, anonymous DataONE otherwise
  (D1–D3). A bad key is an error, never a silent downgrade.
- Read-only v1; downloads exist only on stdio, confined to `downloads.directory`.
- Transports: stdio and stateless Streamable HTTP at `/mcp` (+ `/healthz`, `/readyz`);
  no SSE, no sessions, no roots/sampling/logging.
- Config: `EDI_MCP_<SECTION>__<FIELD>`; precedence flag > env > YAML > defaults; key from
  `EDI_API_KEY` only; no key flag; `.env` is not auto-loaded.
- MIT, Copyright (c) 2026 The Regents of the University of New Mexico.

## EDI facts that drive the code (details and dates in RESEARCH.md)

- Since 2026-07-30 **every** PASTA endpoint needs credentials; anonymous calls get 403
  "Public Access … not authorized". PASTA does not accept `Authorization: Bearer`.
- DataONE serves EDI content anonymously: CN Solr search, GMN `/object` + `/meta`
  (`gmn.lternet.edu` for `knb-lter-*`, `gmn.edirepository.org` for `edi.*`). GMN proxies
  PASTA. CN Solr lags new uploads and indexes non-obsoleted revisions.
- `cite.edirepository.org` works anonymously (ESIP, DRYAD, BIBTEX styles).
- Package ids are `scope.identifier.revision`; DOIs are `doi:10.6073/pasta/<md5>`.

## Security rules

- The API key and any `edi-token` go only to EDI hosts, are never logged, cached in
  clear, echoed, or placed in MRTR `requestState`. Every surfaced URL passes `scrub_url()`.
- Over HTTP, a per-caller `X-EDI-Key` header needs an `https://` `public_base_url`; the
  MCP-level bearer token is never forwarded upstream.
- EML and Solr XML are parsed with defusedxml only.
- Never commit `.env`, `probe.json` with secrets, or unscrubbed fixtures.
