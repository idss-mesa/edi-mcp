# edi-mcp — design

Status: **scaffold, 2026-10-17.** Target: MCP **2026-07-28** (stateless core) on the
Python `mcp` SDK 2.x (`mcp>=2.0,<3`), Python 3.11+. Repo
`https://github.com/idss-mesa/edi-mcp`, package `edi_mcp`, console script `edi-mcp`,
tool prefix `edi_`, MIT (Regents of UNM). Template: `idss-mesa/neon-mcp` at `main`
(a5949d2); its D-register applies wherever this file is silent.

## Decisions register

| # | Question | Decision | Why |
|---|---|---|---|
| D1 | Upstream backend | **Hybrid.** `PastaBackend` when `EDI_API_KEY` is configured, `DataOneBackend` otherwise. Both implement one `Backend` protocol and are normalized into one output model per tool; `source.backend` names the one used. | PASTA has been auth-only since 2026-07-30; DataONE still serves EDI anonymously. |
| D2 | Bad key | PASTA 401/403 with a key → `upstream_forbidden` error. Never fall back to DataONE silently. | A silent downgrade hides misconfiguration and changes result semantics. |
| D3 | PASTA-only tools without a key | `edi_get_quality_report`, `edi_get_lineage`, `edi_recent_changes`, `edi_get_read_counts`, `edi_download_package` return `auth_required` with a hint to `edi://guide/api-key`. `edi_list_scopes` falls back to a static snapshot. | No DataONE equivalent. |
| D4 | Credential form | **Cookie primary, `?key=` fallback** (Step 1 probe, 2026-10-17: both return 200 on all 15 read methods tested). Exchange the key → `edi-token` (`POST auth.edirepository.org/auth/v1/key`), hold it in memory only, refresh with `/auth/v1/token/refresh` when < 1 h of the 8 h lifetime remains, and re-exchange once on a 401 from PASTA. Send it as `Cookie: edi-token=…` to PASTA hosts only. If the auth service is unreachable, use `?key=`, and `scrub_url()` every surfaced URL. | Keeps the long-lived key out of URLs, logs and cache keys while staying available if the IAM service is down. |
| D5 | Key config | `EDI_API_KEY` (env only), overridden by `EDI_MCP_EDI__API_KEY`; other names (`EDI_TOKEN`, `EDI_KEY`) are ignored with a warning; no flag; no `.env` autoload. | neon-mcp D18 pattern. |
| D6 | HTTP per-caller key | `X-EDI-Key` header, honoured only when `server.public_base_url` is https (or `allow_insecure_header_key`). Operator key not shared over HTTP by default. MCP bearer never forwarded. | neon-mcp D10 pattern; spec forbids token passthrough. |
| D7 | Write scope | Read-only v1. `edi_evaluate_package` (dry run) is a later opt-in. | User decision 2026-10-17. |
| D8 | XML safety | defusedxml for EML, Solr XML, resource maps and reports. EML is projected to a compact model **before** `fit_to_budget`; raw EML only via `edi://packages/{packageId}/eml`. | EML is untrusted and can be megabytes. |
| D9 | Identifier input | One resolver accepts `scope.id.rev`, `scope/id/rev`, `scope.id` + `revision=newest\|oldest`, `doi:10.6073/pasta/<md5>` / doi.org URLs, portal `mapbrowse` URLs and PASTA URLs; echoes `packageId` in `resolved`. Scope names fuzzy-resolve (neon resolve thresholds). | Agents paste whatever they found. |
| D10 | Downloads | `edi_download_entities` (batch) and `edi_download_package` (zip): stdio only, `readOnlyHint=false`, `destructiveHint=false` (no overwrite mode), SHA-1 verified, `.part` files. | neon-mcp D3. |
| D12 | DataONE revisions | Parse the revision from the Solr `id`; never follow `obsoletes`/`obsoletedBy` (missing on some superseded revisions, malformed on others). Search and listings de-duplicate per `scope.identifier`, keeping the highest revision; `numFound` is reported as an upper bound. | Verified 2026-10-17 on knb-lter-hbr.14 and knb-lter-jrn.210548103. |
| D13 | Fixtures | Recorded live through the real backends by `scripts/record_fixtures.py`; auth traffic and response headers are never stored; bodies are scrubbed (key, tokens, JWT shapes, token identity claims) before writing; a second pass re-scrubs earlier files; `check` gates promotion and runs in CI. Tests replay them through `FixtureRouter`, which enforces PASTA's credential rules and fails on credentials sent to any other host. | The Step 1 probe leaked a token prefix by truncating before scrubbing. |
| D11 | Registry | Ship `server.json` (`io.github.idss-mesa/edi-mcp`, PyPI `edi-mcp`, `EDI_API_KEY` optional secret). | None of the sibling servers has one. |

## Tool surface (v1)

See the plan table reproduced in README once tools land: `edi_ping`,
`edi_search_packages`, `edi_list_scopes`, `edi_list_identifiers`, `edi_list_revisions`,
`edi_get_package`, `edi_get_metadata`, `edi_list_entities`, `edi_preview_entity`,
`edi_get_citation`, `edi_get_quality_report`, `edi_get_lineage`, `edi_recent_changes`,
`edi_get_read_counts`, `edi_download_entities`, `edi_download_package`.

Resources: `edi://guide/{agent-workflow,api-key,citing-edi-data,package-identifiers,search-syntax}`,
`edi://reference/{scopes,solr-fields}`, templates `edi://packages/{packageId}` and
`edi://packages/{packageId}/eml`. Prompts: `edi_find_data`, `edi_cite_package`,
`edi_plan_download`.
