---
title: "Configuration"
description: "Configure edi-mcp with a YAML file, EDI_MCP_ environment variables or command-line flags; precedence rules, the EDI API key, and every setting with its default."
type: Reference
tags:
  - getting-started
  - configuration
  - environment
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: config-module
    resource: "https://github.com/idss-mesa/edi-mcp/blob/main/src/edi_mcp/config.py"
    title: "edi-mcp configuration model (config.py)"
    author: "team:idss-mesa"
status: stable
---

# Configuration

edi-mcp runs with no configuration at all: the defaults serve stdio, cache upstream
responses in memory, keep tool results small and confine downloads to
`~/edi-downloads`. Settings come from four layers; a higher layer wins:

1. **Command-line flags** (only a handful of common settings).
2. **Environment variables** named `EDI_MCP_<SECTION>__<FIELD>`, with a double
   underscore descending into nested sections at any depth, for example
   `EDI_MCP_EDI__RETRIES__MAX_ATTEMPTS=5`. List settings take a comma-separated value:
   `EDI_MCP_SERVER__ALLOWED_HOSTS=edi.example.org,alt.example.org`. The empty string,
   `none` and `null` mean "unset".
3. **A YAML file** passed with `--config path.yaml`, using the same section and field
   names.
4. **Built-in defaults** (the table below).

Unknown keys in the YAML file or the environment are ignored with a warning, so a typo
does not stop the server but is visible in its log. The loader only checks the shape of
the settings; it never contacts EDI.

## The EDI API key

The key is the only secret, and it is read from the environment only. Set
`EDI_API_KEY`, the name EDI's own guides use. `EDI_MCP_EDI__API_KEY`, when set, takes
precedence (for giving edi-mcp a different key from your other EDI tools). Look-alike
names (`EDI_KEY`, `EDI_TOKEN`, `EDI_AUTH_TOKEN`) are **not** read; edi-mcp logs a
warning if one of them is set without `EDI_API_KEY`. There is deliberately **no
command-line flag** for the key: arguments are visible to every user in the process
list and end up in shell history. edi-mcp does not load `.env` files itself; if you
keep the key in one, export it into the environment before starting the server. See
[EDI API key](api-key.md) for creating a key and checking that EDI accepts it.

The key decides the backend: with one, edi-mcp reads PASTA; without one, it reads the
anonymous DataONE replicas ([Backends](../tools/backends.md)).

## Command-line flags

| Flag | Sets |
| --- | --- |
| `--config PATH` | YAML file to load |
| `--transport {stdio,http}` | `server.transport` |
| `--bind-address`, `--bind-port` | `server.bind_address`, `server.bind_port` |
| `--log-level` | `server.log_level` |
| `--download-dir PATH` | `downloads.directory` |
| `--no-downloads` | `downloads.enabled = false` |
| `--print-config` | print the effective configuration as YAML (key shown as `***`) and exit |
| `--check` | load the configuration, call `edi_ping` in-process (no network request), print a JSON report, exit 0 or 1 |
| `--version` | print the version |

## A YAML example

```yaml
# edi-mcp.yaml — pass with: edi-mcp --config edi-mcp.yaml
edi:
  max_concurrency: 4
  retries:
    max_attempts: 3
cache:
  ttl_s:
    search: 600
limits:
  max_result_bytes: 50000
downloads:
  directory: /data/edi-downloads
server:
  log_level: info
```

Never put the API key in a YAML file you share or commit; use `EDI_API_KEY`.

## Automatic values

A few settings default to "unset" and resolve per transport:

* `downloads.enabled`: downloads exist only on stdio; over HTTP the download tools are
  never listed, whatever this says. `--no-downloads` turns them off on stdio too. See
  [Previews and downloads](../tools/data.md).
* `server.dns_rebinding_protection`: unset follows the MCP SDK default, which is on for
  loopback binds or when `allowed_hosts` / `allowed_origins` are set.
* `server.public_base_url`: when set, its host and origin join the allow-lists, and an
  `https://` URL enables per-caller keys in the `X-EDI-Key` header (see
  [Hosted HTTP deployment](../deploy/hosted-http.md)).

## All settings

<!-- BEGIN GENERATED CONFIG (scripts/gen_config_reference.py; do not edit) -->

| Setting (YAML path) | Environment variable | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `edi.pasta_base_url` | `EDI_MCP_EDI__PASTA_BASE_URL` | str | `https://pasta.lternet.edu` | PASTA+ base URL (package and audit services). |
| `edi.auth_base_url` | `EDI_MCP_EDI__AUTH_BASE_URL` | str | `https://auth.edirepository.org/auth/v1` | EDI Identity and Access Manager API (key -> edi-token exchange). |
| `edi.dataone_cn_url` | `EDI_MCP_EDI__DATAONE_CN_URL` | str | `https://cn.dataone.org/cn/v2` | DataONE coordinating node (Solr search, resolve) used without a key. |
| `edi.gmn_lter_url` | `EDI_MCP_EDI__GMN_LTER_URL` | str | `https://gmn.lternet.edu/mn/v2` | DataONE member node serving knb-lter-* packages without a key. |
| `edi.gmn_edi_url` | `EDI_MCP_EDI__GMN_EDI_URL` | str | `https://gmn.edirepository.org/mn/v2` | DataONE member node serving edi.* and other non-LTER packages without a key. |
| `edi.cite_url` | `EDI_MCP_EDI__CITE_URL` | str | `https://cite.edirepository.org/cite` | EDI citation service (anonymous). |
| `edi.portal_url` | `EDI_MCP_EDI__PORTAL_URL` | str | `https://portal.edirepository.org/nis` | EDI Data Portal (landing pages are built from it). |
| `edi.api_key` | `EDI_MCP_EDI__API_KEY`<br>(or `EDI_API_KEY`) | SecretStr \| null | unset | EDI API access key (https://auth.edirepository.org/auth/ui/key). Enables the PASTA backend; without it edi-mcp uses DataONE. Prefer the EDI_API_KEY env var; never commit it. |
| `edi.user_agent_suffix` | `EDI_MCP_EDI__USER_AGENT_SUFFIX` | str \| null | unset | Text appended to the User-Agent header. |
| `edi.max_token_slots` | `EDI_MCP_EDI__MAX_TOKEN_SLOTS` | int | `256` | Most per-caller key/token slots kept in memory (HTTP X-EDI-Key callers; least recently used are dropped first). |
| `edi.connect_timeout_s` | `EDI_MCP_EDI__CONNECT_TIMEOUT_S` | float | `10.0` | TCP/TLS connect timeout. |
| `edi.read_timeout_s` | `EDI_MCP_EDI__READ_TIMEOUT_S` | float | `60.0` | Default read timeout. |
| `edi.download_read_timeout_s` | `EDI_MCP_EDI__DOWNLOAD_READ_TIMEOUT_S` | float | `300.0` | Read timeout for data-entity downloads. |
| `edi.max_concurrency` | `EDI_MCP_EDI__MAX_CONCURRENCY` | int | `4` | Maximum simultaneous upstream requests. |
| `edi.token_refresh_margin_s` | `EDI_MCP_EDI__TOKEN_REFRESH_MARGIN_S` | float | `3600.0` | Refresh the 8-hour edi-token once fewer than this many seconds remain. |
| `edi.auth_fallback_s` | `EDI_MCP_EDI__AUTH_FALLBACK_S` | float | `300.0` | After the EDI auth service fails, send ?key= for this long before retrying it. |
| `edi.max_response_bytes` | `EDI_MCP_EDI__MAX_RESPONSE_BYTES` | int | `20971520` | Largest upstream response body read into memory. |
| `edi.retries.max_attempts` | `EDI_MCP_EDI__RETRIES__MAX_ATTEMPTS` | int | `3` | Attempts per upstream call, including the first. |
| `edi.retries.backoff_base_s` | `EDI_MCP_EDI__RETRIES__BACKOFF_BASE_S` | float | `0.5` | Base of the exponential backoff (0.5 * 2^n seconds). |
| `edi.retries.backoff_max_s` | `EDI_MCP_EDI__RETRIES__BACKOFF_MAX_S` | float | `8.0` | Cap on a single backoff sleep. |
| `edi.retries.retry_after_default_s` | `EDI_MCP_EDI__RETRIES__RETRY_AFTER_DEFAULT_S` | float | `1.0` | Wait used on HTTP 429 when no Retry-After header is sent. |
| `cache.enabled` | `EDI_MCP_CACHE__ENABLED` | bool | `true` | Cache upstream responses in memory. |
| `cache.max_entries` | `EDI_MCP_CACHE__MAX_ENTRIES` | int | `1024` | Overall entry cap across families. |
| `cache.stale_if_error_s` | `EDI_MCP_CACHE__STALE_IF_ERROR_S` | int | `86400` | How long an expired entry may be served when a refresh fails. |
| `cache.ttl_s.listings` | `EDI_MCP_CACHE__TTL_S__LISTINGS` | int | `3600` | Scope, identifier and revision listings. |
| `cache.ttl_s.search` | `EDI_MCP_CACHE__TTL_S__SEARCH` | int | `600` | Search results. |
| `cache.ttl_s.metadata` | `EDI_MCP_CACHE__TTL_S__METADATA` | int | `86400` | EML and entity facts of a given revision (immutable upstream). |
| `cache.ttl_s.reports` | `EDI_MCP_CACHE__TTL_S__REPORTS` | int | `86400` | Quality reports and provenance. |
| `cache.ttl_s.feeds` | `EDI_MCP_CACHE__TTL_S__FEEDS` | int | `300` | Change and upload feeds, read counts. |
| `cache.ttl_s.citations` | `EDI_MCP_CACHE__TTL_S__CITATIONS` | int | `86400` | Formatted citations. |
| `limits.default_limit` | `EDI_MCP_LIMITS__DEFAULT_LIMIT` | int | `25` | Default page size where a tool does not set its own. |
| `limits.max_limit` | `EDI_MCP_LIMITS__MAX_LIMIT` | int | `200` | Largest page size any tool accepts. |
| `limits.max_result_bytes` | `EDI_MCP_LIMITS__MAX_RESULT_BYTES` | int | `50000` | Tool results are trimmed (with page.truncated) to fit this many bytes of compact JSON. |
| `limits.hard_max_result_bytes` | `EDI_MCP_LIMITS__HARD_MAX_RESULT_BYTES` | int | `200000` | A result still larger than this after trimming fails with result_too_large. |
| `limits.text_budget_summary` | `EDI_MCP_LIMITS__TEXT_BUDGET_SUMMARY` | int | `300` | Characters kept of long text fields (abstracts) in summaries. |
| `limits.text_budget_detail` | `EDI_MCP_LIMITS__TEXT_BUDGET_DETAIL` | int | `4000` | Default characters kept of long text fields in detail views. |
| `limits.max_eml_bytes` | `EDI_MCP_LIMITS__MAX_EML_BYTES` | int | `20971520` | Largest EML document parsed (larger ones fail with result_too_large). |
| `limits.max_resource_bytes` | `EDI_MCP_LIMITS__MAX_RESOURCE_BYTES` | int | `1048576` | Largest resource read returned (the raw EML template); larger ones fail with result_too_large. |
| `limits.preview_max_bytes` | `EDI_MCP_LIMITS__PREVIEW_MAX_BYTES` | int | `262144` | Most bytes edi_preview_entity reads from an entity. |
| `limits.tools_list_max_bytes` | `EDI_MCP_LIMITS__TOOLS_LIST_MAX_BYTES` | int | `60000` | Conformance bound on the serialized tools/list result (58 KB with all 16 tools). |
| `downloads.enabled` | `EDI_MCP_DOWNLOADS__ENABLED` | bool \| null | unset | Offer the download tools. Unset: true on stdio; never available over http. |
| `downloads.directory` | `EDI_MCP_DOWNLOADS__DIRECTORY` | Path | `~/edi-downloads` | Directory every download is confined to (created on first use). |
| `downloads.max_files_per_call` | `EDI_MCP_DOWNLOADS__MAX_FILES_PER_CALL` | int | `50` | Most entities one edi_download_entities call transfers. |
| `downloads.max_bytes_per_call` | `EDI_MCP_DOWNLOADS__MAX_BYTES_PER_CALL` | int | `2147483648` | Most bytes one download call transfers. |
| `downloads.max_file_bytes` | `EDI_MCP_DOWNLOADS__MAX_FILE_BYTES` | int | `1073741824` | Largest single file accepted. |
| `downloads.verify_checksums` | `EDI_MCP_DOWNLOADS__VERIFY_CHECKSUMS` | bool | `true` | Verify the SHA-1 checksums EDI publishes. |
| `downloads.allowed_hosts` | `EDI_MCP_DOWNLOADS__ALLOWED_HOSTS` | list[str] | `[pasta.lternet.edu, gmn.lternet.edu, gmn.edirepository.org, cn.dataone.org]` | Hosts downloads (and their redirects) may come from; '*.' is a subdomain wildcard. |
| `server.transport` | `EDI_MCP_SERVER__TRANSPORT` | `stdio` \| `http` | `stdio` | stdio (local clients) or http (stateless Streamable HTTP at /mcp). |
| `server.bind_address` | `EDI_MCP_SERVER__BIND_ADDRESS` | str | `127.0.0.1` | HTTP bind address. |
| `server.bind_port` | `EDI_MCP_SERVER__BIND_PORT` | int | `8080` | HTTP bind port. |
| `server.public_base_url` | `EDI_MCP_SERVER__PUBLIC_BASE_URL` | str \| null | unset | Public URL of a hosted deployment; its host/origin join the allow-lists and https:// enables per-request keys. |
| `server.allowed_hosts` | `EDI_MCP_SERVER__ALLOWED_HOSTS` | list[str] | `[]` | Host header allow-list (DNS-rebinding protection). |
| `server.allowed_origins` | `EDI_MCP_SERVER__ALLOWED_ORIGINS` | list[str] | `[]` | Origin header allow-list (DNS-rebinding protection). |
| `server.dns_rebinding_protection` | `EDI_MCP_SERVER__DNS_REBINDING_PROTECTION` | bool \| null | unset | Force DNS-rebinding protection on/off. Unset: SDK default (on for loopback binds or when allow-lists are set). |
| `server.json_response` | `EDI_MCP_SERVER__JSON_RESPONSE` | bool | `false` | Answer POST /mcp with application/json instead of a single SSE frame. |
| `server.max_request_body_size` | `EDI_MCP_SERVER__MAX_REQUEST_BODY_SIZE` | int | `1048576` | Largest accepted request body in bytes. |
| `server.accept_header_key` | `EDI_MCP_SERVER__ACCEPT_HEADER_KEY` | bool | `true` | HTTP: honour a per-request EDI API key header (subject to the TLS gate). |
| `server.request_key_header` | `EDI_MCP_SERVER__REQUEST_KEY_HEADER` | str | `X-EDI-Key` | Header carrying a caller's EDI API key in HTTP mode. |
| `server.allow_insecure_header_key` | `EDI_MCP_SERVER__ALLOW_INSECURE_HEADER_KEY` | bool | `false` | Accept header keys when public_base_url is not https:// (development only). |
| `server.share_config_key_over_http` | `EDI_MCP_SERVER__SHARE_CONFIG_KEY_OVER_HTTP` | bool | `false` | Lend the operator's configured key to HTTP callers without one (private deployments only). |
| `server.tools_list_ttl_ms` | `EDI_MCP_SERVER__TOOLS_LIST_TTL_MS` | int | `300000` | ttlMs advertised on tools/list. |
| `server.log_level` | `EDI_MCP_SERVER__LOG_LEVEL` | `debug` \| `info` \| `warning` \| `error` \| `critical` | `info` | Log verbosity. |
| `server.instructions_extra` | `EDI_MCP_SERVER__INSTRUCTIONS_EXTRA` | str \| null | unset | Text appended to the server instructions. |

<!-- END GENERATED CONFIG -->
