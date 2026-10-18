# Changelog

All notable changes to edi-mcp are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Core server ported from neon-mcp: tool registry with result-size budget and MRTR
  continuations, MCP 2026-07-28 adapter (structured results, cache hints,
  `server/discover`), config loader (`EDI_MCP_*`, `EDI_API_KEY`), structured errors
  (`auth_required`, `upstream_forbidden`, …), EDI API key resolution with the HTTP TLS
  gate (`X-EDI-Key`), stdio and stateless Streamable HTTP transports with `/healthz` and
  `/readyz`.
- `edi_ping` tool: version, protocol, key status and which backend serves the caller.
- Resources `edi://guide/api-key` and `edi://guide/package-identifiers`.
- `scripts/probe_auth.py`: checks which credential forms PASTA accepts.
- CI: lint, types, tests on Python 3.11–3.13, macOS subset, MCP 2026-07-28 conformance.
- Upstream client: API key → `edi-token` exchange with refresh, one re-exchange on 401
  and a `?key=` fallback when the auth service is down; credentials sent to PASTA only;
  a cookie jar that never stores PASTA's `Set-Cookie`; retries, allow-listed redirects,
  byte caps and a per-family TTL cache.
- PASTA and DataONE backends behind one contract (search, listings, EML, entities,
  checksums, DOIs), the identifier parser (package ids, DOIs, portal and PASTA URLs) and
  hardened XML parsing.
- `edi_ping(check_api=true)`: one request to the caller's backend to confirm the key and
  connectivity.
- Recorded, scrubbed fixtures with a replaying test router, `scripts/record_fixtures.py`
  (`record`, `check`), live smoke tests and a nightly CI job.
- Discovery tools on both backends: `edi_search_packages` (free text, scope, creator,
  temporal overlap, bounding box, sort by publication date, paging),
  `edi_list_scopes` (live with a key, a dated snapshot without), `edi_list_identifiers`
  and `edi_list_revisions`.
- Scope names and LTER site codes are accepted wherever a scope is (`Jornada`, `JRN`,
  `jrn.210548103`), echoed in `resolved`; shared names return `ambiguous_input`.
- Resource `edi://reference/scopes`: every scope with name, kind, site code, location
  and package counts on PASTA and DataONE.

### Changed

- `lter-landsat-ledaps` joins `ecotrends` and `lter-landsat` as a bulk scope excluded
  from search by default.
- A PASTA 403 sent with valid credentials is now `upstream_forbidden` with
  `reason: access_restricted` (the package is restricted) instead of a message blaming
  the key.

### Security

- Upstream error text no longer carries the key owner's display name from PASTA's
  `User '…' is not authorized` messages.
