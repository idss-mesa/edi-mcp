# CLAUDE.md — edi-mcp

edi-mcp is a Model Context Protocol server (MCP **2026-07-28**, stateless core) for the
Environmental Data Initiative (EDI) PASTA+ repository, published at
https://github.com/idss-mesa/edi-mcp. Python 3.11+, `mcp>=2.0,<3` (low-level `Server`),
pydantic v2, httpx, structlog, defusedxml. It is a sibling of `idss-mesa/neon-mcp` and
copies its architecture (registry, server adapter, envelope, transports, tests).
`DESIGN.md` records every decision (the D-numbers) and `RESEARCH.md` the verified API
facts; read them before changing behaviour.

## Status

Build order (one PR each): 1 scaffold + auth probe ✅ → 2 core port from neon-mcp ✅
(registry, adapter, config, errors, key resolution, transports, `edi_ping`, conformance
tests, CI) → 3 client/token exchange/PID resolver/backends + fixtures ✅ → 4 discovery tools
(search, list scopes/identifiers/revisions, D9 scope names) ✅ → 5 package, metadata and
entity tools (EML projection) ✅ → 6 preview/download/citation/PASTA-only tools → 7 resources, prompts, docs, server.json, Docker, v0.1.0.
`--check` stays offline (the live check is `edi_ping(check_api=true)`). Tool descriptions
and `nextSteps` already name step-6 tools (`edi_preview_entity`, `edi_download_entities`,
`edi_get_citation`). `resources_static/scopes.json` is a dated snapshot; the live test
`test_live_scope_snapshot_is_current` fails when a known scope leaves PASTA (new ones warn).
tools/list is 38 KB with 8 of 16 tools (bound 60 KB): re-measure in step 7.

## Commands

```bash
uv sync --all-extras
uv run pytest                                   # hermetic unit + conformance tests
uv run ruff check src tests scripts && uv run ruff format --check src tests
uv run mypy --strict src
uv run python scripts/record_fixtures.py check  # fixtures carry no secrets (CI runs it)
scripts/install.sh --agents all --dry-run       # register with agents (test only in a sandboxed HOME)
uv run zensical build --clean --strict          # docs; then gen_tools_reference.py / gen_llms_txt.py
set -a; . ./.env; set +a; uv run python scripts/record_fixtures.py record   # re-record live
set -a; . ./.env; set +a; EDI_MCP_LIVE=1 uv run pytest -m live tests/live   # live smoke
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

## Code map

`server.py` is the only SDK-coupled module (adapter); `registry.py` validates tools,
fails fast with `auth_required` for `requires_key` tools and enforces the result budget;
tools in `tools/<family>.py` are `async (args, ctx) -> OutputModel`; `context.py`
resolves the call's key and backend (`ctx.backend` is `pasta` or `dataone`);
`edi/auth.py` holds `ApiKey`, the HTTP TLS gate and `scrub_url`; `edi/tokens.py`
exchanges/refreshes the key for an `edi-token` (per key identity, `?key=` fallback);
`edi/client.py` is the one httpx client (credentials to PASTA only, cookie jar that
stores nothing, retries, allow-listed redirects, byte caps, cache); `edi/backends/`
holds `PastaBackend` and `DataOneBackend` behind one contract — tools call
`backend_for(ctx)` and `resolve_package(...)`, never the client directly; `edi/pid.py`
parses identifiers; `edi/scopes.py` loads the scope snapshot and resolves scope names,
site codes and `name.identifier` references (D9) — tools call `resolve_scope` /
`resolve_reference` (or `resolve_package`, which uses it); `edi/xml.py` (defusedxml; `prose()` for EML text) and
`edi/eml.py` (entity refs); `projections/eml.py` projects a parsed EML into compact capped
models (D15); package tools in `tools/packages.py` fetch and parse the EML once (`load()`). Tests replay `tests/fixtures/` through `tests/fixture_router.py`
(any unrecorded request fails); `scripts/record_fixtures.py` records
backend scenarios and `TOOL_SCENARIOS` (real tool calls on both backends); transports in
`transport/`; static guides and `scopes.json` in `resources_static/`; tool helpers
(`source`, `paginate`, `portal_url`) in `tools/_common.py`.

## Adding a tool

Models (`EdiInput` / `ToolResultBase`, every input field described) → `@register_tool`
(name `^edi_[a-z_]+$`, description ≤ 600 chars ending in a `Next:` sentence, honest
annotations, every upstream endpoint listed, `requires_key=True` for PASTA-only tools)
→ import in `tools/__init__.py` → tests via `tests.helpers.call_ok` (validates
`outputSchema`) → update the `KEY_TOOLS` / `WRITE_TOOLS` sets in the conformance test.

## EDI facts that drive the code (details and dates in RESEARCH.md)

- Since 2026-07-30 **every** PASTA endpoint needs credentials; anonymous calls get 403
  "Public Access … not authorized". PASTA does not accept `Authorization: Bearer`.
- DataONE serves EDI content anonymously: CN Solr search, GMN `/object` + `/meta`
  (`gmn.edirepository.org` for scope `edi`, `gmn.lternet.edu` otherwise; CN `/object`
  as fallback). GMN proxies PASTA. CN Solr lags new uploads; its `obsoletedBy` /
  `obsoletes` are unreliable, so revisions come from parsing `id` and results are
  de-duplicated per `scope.identifier`.
- PASTA's data entity id is the MD5 of the EML `entityName`.
- PASTA search sorts only with `sort=pubdate,desc`; the space form is silently ignored,
  so live tests assert result order, not just HTTP 200. Malformed spatial `fq` is a 500.
- DataONE drifts: on 2026-10-19 its `pubDate` became unsortable (sort by `dateUploaded`)
  and legacy `scope.id.rev` ids surfaced. Never assert DataONE ranking in tests.
- Both GMN member nodes serve data anonymously (`anonymousUrl`); GMN ignores `Range`.
- Bulk scopes `ecotrends`, `lter-landsat`, `lter-landsat-ledaps` (~36k records) are
  excluded from search unless asked for. Revision 0 exists (`msb-paleon.31.0`).
- A credentialed PASTA 403 means an access-restricted package (a bad key gets 401); the
  403 text names the caller, so the client strips `User '…'` from upstream errors.
- PASTA sets an `edi-token` cookie even on anonymous 403s; it must never be stored.
- `cite.edirepository.org` works anonymously (ESIP, DRYAD, BIBTEX styles).
- Package ids are `scope.identifier.revision`; DOIs are `doi:10.6073/pasta/<md5>`.

## Security rules

- The API key and any `edi-token` go only to EDI hosts, are never logged, cached in
  clear, echoed, or placed in MRTR `requestState`. Every surfaced URL passes `scrub_url()`.
- Over HTTP, a per-caller `X-EDI-Key` header needs an `https://` `public_base_url`; the
  MCP-level bearer token is never forwarded upstream.
- EML and Solr XML are parsed with defusedxml only.
- Never commit `.env`, `probe.json` with secrets, or unscrubbed fixtures. Fixtures come
  only from `scripts/record_fixtures.py record` (scrubs before writing, records no auth
  traffic or headers, promotes only if `check` passes).
