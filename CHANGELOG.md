# Changelog

All notable changes to edi-mcp are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-20

First release, on PyPI as **`edi-pasta-mcp`** (the name `edi-mcp` belongs to an
unrelated project); it installs the commands `edi-mcp` and `edi-pasta-mcp`.

### Added

- Build step 7: guides `edi://guide/agent-workflow`, `edi://guide/citing-edi-data` and
  `edi://guide/search-syntax`; resource templates `edi://packages/{packageId}` (the
  `edi_get_package` summary) and `edi://packages/{packageId}/eml` (raw EML, at most
  1 MiB), served with `cacheScope: private` because they depend on the caller's key
  (D21); prompts `edi_find_data`, `edi_cite_package` and `edi_plan_download` (D22).
- `server.json` for the MCP Registry (`io.github.idss-mesa/edi-mcp`), a Dockerfile
  (non-root, read-only root file system, `/healthz` health check) with
  `docker-compose.yml`, `scripts/smoke_http.py`, a CI job that builds and smoke-tests the
  image, and `release.yml` (PyPI trusted publishing, GitHub release, MCP Registry).

- Build step 6: `edi_preview_entity` (first rows of a delimited entity, streamed and
  stopped early; EML layout, header detection, binary refused), `edi_download_entities`
  and `edi_download_package` (stdio only; caps checked first, SHA-1 verified, EML saved,
  safe file names, never overwrites), `edi_get_citation` (ESIP, DRYAD, BibTeX and parts
  from cite.edirepository.org), `edi_get_quality_report` (counts and non-valid checks;
  works without a key via the DataONE member nodes, D18), and the key-only
  `edi_get_lineage`, `edi_recent_changes` (uploader principals dropped) and
  `edi_get_read_counts`. The client gains one streaming path (`stream()`); output schemas
  fold nullable `anyOf` so `tools/list` stays under 60 KB with 16 tools (D20).
- `scripts/install.sh` registers edi-mcp with Claude Code, Claude Desktop, Codex CLI,
  Gemini CLI, Goose and OpenCode (detects installed agents; `--dry-run`, `--scope`,
  `--uninstall`, Git Bash path conversion on Windows). `--with-key` stores the EDI API
  key from the environment or a hidden prompt; there is no key flag, `--env` refuses the
  key, output masks it and key-bearing config files are written owner-only. Hermetic
  tests run it in a sandboxed HOME.
- Documentation site at https://idss-mesa.github.io/edi-mcp/ (Zensical, OKF v0.2,
  generated tool and configuration references, `llms.txt`), with installation
  instructions for macOS, Linux and Windows.
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
- Package tools on both backends: `edi_get_package` (overview, DOI, newest revision,
  license, entities and total size), `edi_get_metadata` (EML projected to overview,
  people, coverage, methods, rights, project and entity sections) and `edi_list_entities`
  (columns with units, codes and missing values, CSV layout, optional SHA-1, PASTA and
  anonymous DataONE URLs).
- EML projection with inline-markup-aware text, `<references>` resolution and capped
  lists with totals.

### Changed

- Per-caller token slots and the log redactor's secret set are bounded LRUs; the
  configured key is never evicted (D23).
- Empty `EDI_MCP_*` environment values count as unset.
- The server instructions point at `edi://guide/agent-workflow` and
  `edi://guide/search-syntax`.

- `lter-landsat-ledaps` joins `ecotrends` and `lter-landsat` as a bulk scope excluded
  from search by default.
- DataONE sorts search results by upload date: its `pubDate` became unsortable on
  2026-10-19. Legacy `scope.id.rev` identifiers in DataONE's index are now understood, and
  malformed dates dropped.
- A PASTA 403 sent with valid credentials is now `upstream_forbidden` with
  `reason: access_restricted` (the package is restricted) instead of a message blaming
  the key.

### Fixed

- The API-key guide suggested `uvx edi-mcp`, which would install the unrelated PyPI
  project; it now says `uvx edi-pasta-mcp`.

### Security

- Upstream error text no longer carries the key owner's display name from PASTA's
  `User '…' is not authorized` messages.
