---
title: "Security"
description: "How edi-mcp handles EDI API keys and edi-tokens, which hosts receive credentials, how URLs, logs and upstream errors are scrubbed, how untrusted XML is parsed, and what keeps test fixtures free of secrets."
type: Policy
tags:
  - deploy
  - security
  - credentials
  - api-key
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: edi-news
    resource: "https://edirepository.org/news/news-20260727.00"
    title: "EDI news: authentication required for PASTA (2026-07-27)"
    author: "team:edi"
  - id: edi-keys
    resource: "https://edirepository.org/resources/working-with-access-keys"
    title: "EDI — Working with access keys"
    author: "team:edi"
  - id: mcp-security
    resource: "https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices"
    title: "MCP 2026-07-28 — Security best practices"
    author: "team:modelcontextprotocol"
  - id: defusedxml
    resource: "https://github.com/tiran/defusedxml"
    title: "defusedxml — XML bomb protection for Python stdlib modules"
    author: "team:defusedxml"
status: stable
---

# Security

Since 2026-07-30 every PASTA endpoint needs credentials[^edi-news], so an EDI
API key is a real secret: it reads everything its owner can read, including
access-restricted packages. edi-mcp treats it accordingly. Version 1 is
**read-only**: no tool creates, updates or deletes anything in EDI, and the
only local writes will be the stdio-only downloads, confined to
`downloads.directory`.

## Where the key comes from

* **stdio:** the server's environment only. `EDI_API_KEY` (the name EDI's
  guides use[^edi-keys]) or `EDI_MCP_EDI__API_KEY`, which overrides it. There
  is no command-line flag (command lines leak into `ps` and shell history),
  `.env` files are not loaded automatically, and look-alike names
  (`EDI_KEY`, `EDI_TOKEN`, `EDI_AUTH_TOKEN`) are not read: the loader warns
  when one is set without `EDI_API_KEY`. A YAML `edi.api_key` also works but
  should not be committed.
* **HTTP:** each caller's `X-EDI-Key` header, honoured only when
  `server.public_base_url` is `https://` (or the development override
  `allow_insecure_header_key` is on); otherwise the header is stripped before
  any handler runs. The operator's key is not lent to callers unless
  `share_config_key_over_http` is enabled. The MCP-level `Authorization`
  header is never read for EDI and never forwarded upstream[^mcp-security].
  See [Hosted HTTP deployment](hosted-http.md).

A bad key is an error (`upstream_forbidden`), never a silent downgrade to
DataONE.

## What happens to the key

* The key is held in an `ApiKey` object whose `repr` and `str` never show it,
  and every key and token the process sees is registered with the log
  redactor.
* The key is exchanged for a short-lived `edi-token` (8 hours) at
  `auth.edirepository.org`. Tokens live in memory only, one slot per key
  identity (a truncated SHA-256 of the key), so HTTP callers with different
  keys never share a token. A token is refreshed once fewer than
  `edi.token_refresh_margin_s` seconds remain (default one hour); a 401 to a
  token triggers one re-exchange.
* The token is sent to PASTA as a hand-set `Cookie: edi-token=…` header. If
  the auth service is unreachable or failing, the key itself is sent as a
  `?key=` query parameter for `edi.auth_fallback_s` seconds (default 300). If
  the auth service rejects the key, the call fails.
* Credentials are attached **only** to requests for the PASTA host. DataONE,
  the member nodes and the citation service are always called anonymously.
* The HTTP client's cookie jar accepts no cookies, so the `edi-token` cookie
  PASTA sets (even on anonymous 403 responses) is never stored or replayed to
  another caller.
* Cached PASTA responses are keyed by the key's identity, so one caller's
  cached results are never served to another caller.

## What never leaves the server

* `scrub_url()` removes the `key` query parameter and redacts every
  registered secret from each URL that is surfaced: result `source` fields,
  `_meta` upstream labels, log lines, cache keys and error details. Endpoint
  labels (`GET host/path`) carry no query string at all.
* HTTP transport errors are re-raised without the underlying exception, whose
  message could contain a keyed URL.
* Logs go to stderr (stdout is MCP framing on stdio). A structlog processor
  masks values of credential-like keys (`token`, `authorization`, `api_key`,
  `x-edi-key`, `cookie`, …) and replaces registered secrets anywhere in a
  logged string.
* Upstream error text is cleaned before it reaches a result: registered
  secrets are redacted, EDI principals (`EDI-<40 hex>`) become `EDI-…`, and
  PASTA's 403 wording `User '…' is not authorized`, which names the caller,
  has the name removed.
* MRTR continuations (`requestState`) refuse credential-like keys and are
  capped at 16 KiB.

## Outbound requests

* Upstream hosts come from the `edi.*` URL settings: PASTA, the EDI auth
  service, the DataONE coordinating node, the two GMN member nodes and the
  citation service. Redirects are followed by hand, at most three, and only to
  `https://` hosts on that allow-list; anything else fails with an error.
* Response bodies are read with a byte cap (`edi.max_response_bytes`, default
  20 MiB), and EML documents larger than `limits.max_eml_bytes` are refused.
  Tool results are trimmed to `limits.max_result_bytes` and fail above
  `limits.hard_max_result_bytes`.
* Concurrency is bounded (`edi.max_concurrency`); 429 responses honour
  `Retry-After`, and 5xx and network errors are retried with backoff.

## Untrusted XML

EML metadata and DataONE Solr responses are parsed with `defusedxml`[^defusedxml]
only, which rejects entity expansion and external DTDs. Raw EML is not placed in
tool results.

## Test fixtures

Hermetic tests replay recorded responses, so fixtures must never carry a
secret. `scripts/record_fixtures.py record` never records auth-service traffic,
keeps no response headers except `Content-Type` and `Location`, and scrubs every
body before writing it: the key, every `edi-token` seen, anything JWT-shaped,
and the identity claims decoded from the token. Recordings replace the committed
set only if `check` passes; CI runs `check` on every push (no JWT-shaped string,
no `edi-token=`, no `set-cookie`, no `key=` in a manifest URL). The test router
fails a test if a credential reaches any host other than PASTA. See
[Testing](../develop/testing.md).

## Reporting a vulnerability

Report a suspected vulnerability privately to the
[idss-mesa](https://github.com/idss-mesa){target=_blank} maintainers rather than
in a public issue, and never paste a key or token into an issue, log or
fixture.

[^edi-news]: EDI news: authentication required for PASTA (2026-07-27). <https://edirepository.org/news/news-20260727.00>
[^edi-keys]: EDI — Working with access keys. <https://edirepository.org/resources/working-with-access-keys>
[^mcp-security]: MCP 2026-07-28 — Security best practices. <https://modelcontextprotocol.io/specification/2026-07-28/basic/security_best_practices>
[^defusedxml]: defusedxml. <https://github.com/tiran/defusedxml>
