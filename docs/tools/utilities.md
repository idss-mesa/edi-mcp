---
title: "Utilities and errors"
description: "Check the server, its key status and backend with edi_ping, and the stable error codes every edi-mcp tool can return."
type: Reference
tags:
  - tools
  - ping
  - errors
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: registry
    resource: "https://github.com/idss-mesa/edi-mcp/blob/main/src/edi_mcp/errors.py"
    title: "edi-mcp error codes (errors.py)"
    author: "team:idss-mesa"
  - id: mcp-tools
    resource: "https://modelcontextprotocol.io/specification/2026-07-28/server/tools"
    title: "MCP specification — Tools"
    author: "team:modelcontextprotocol"
status: stable
---

# Utilities and errors

## edi_ping

[`edi_ping`](reference.md#edi_ping) is a liveness and capability report. It makes no
upstream request unless asked to, so it is the first thing to call when a client
connects or a tool fails unexpectedly.

| Field | Meaning |
| --- | --- |
| `pong` | Always `ok`. |
| `version`, `protocolVersion` | edi-mcp version and the MCP revision it serves (`2026-07-28`). |
| `transport` | `stdio` or `http`. |
| `keyConfigured` | Whether this call has an EDI API key available. The key itself is never shown. |
| `keySource` | `config` (the server's environment or config file), `request` (an HTTP caller's `X-EDI-Key` header) or `none`. |
| `backend` | `pasta` with a key, `dataone` without one (see [Backends](backends.md)). |
| `keyRequiredTools` | Registered tools that fail with `auth_required` without a key. |
| `downloadsEnabled`, `downloadDir` | Whether download tools are offered on this transport, and where they write. |
| `endpoints` | The PASTA, auth, DataONE and citation base URLs in use. |
| `api` | Present only with `check_api=true`. |

With `check_api=true` edi-mcp makes one small request to the backend serving the
caller — with a key, it exchanges the key for a token and lists PASTA's scopes;
without one, it runs a zero-row DataONE query — and reports in `api`:

| Field | Meaning |
| --- | --- |
| `reachable` | Whether the backend answered. |
| `backend` | The backend that was checked. |
| `credential` | `token` (an `edi-token` cookie), `key` (the key as a query parameter, used only when EDI's auth service is unreachable) or `none` (DataONE). |
| `endpoint`, `latencyMs` | The request made and how long it took. |
| `error` | The error `code` and `message` when the check failed, e.g. `upstream_forbidden` for a rejected key. |

`edi-mcp --check` calls `edi_ping` in-process and prints the report as JSON. It
stays offline; the live check is `edi_ping(check_api=true)`.

## Error codes

A failed tool call returns `isError: true` and
`structuredContent.error = {code, message, details, hint?}`. `code` is stable and
machine-readable; `message` is safe to show a user and never contains a key or token;
`hint`, when present, is a one-line remedy.

| Code | Meaning | What to do |
| --- | --- | --- |
| `invalid_argument` | The arguments failed validation, an identifier could not be parsed, or the upstream rejected the request (HTTP 400). | Fix the argument; `details` names the problem and, for identifiers, lists the accepted forms. |
| `not_found` | No such package, scope, revision or resource (HTTP 404/410), or a scope name matched nothing. | Check the identifier; scope misses include `didYouMean`. |
| `ambiguous_input` | A scope name or location matches several scopes about equally. | Pick one of the ranked `candidates` and pass its exact scope. |
| `auth_required` | The operation needs an EDI API key and none is available for this call. | Set `EDI_API_KEY` (stdio) or send `X-EDI-Key` (HTTP); `details.guide` points at `edi://guide/api-key`. |
| `upstream_forbidden` | A key was sent and EDI refused. Without `reason` (HTTP 401) the key was rejected; with `reason: access_restricted` (HTTP 403) the key works but the package is restricted to named users or groups. | Replace the key, or for a restricted package ask its contact for access. edi-mcp never falls back to DataONE here. |
| `rate_limited` | The upstream answered HTTP 429. | Wait `details.retryAfterSeconds` before retrying. |
| `upstream_error` | The upstream failed (HTTP 5xx), answered with an unexpected status, or returned a body that could not be parsed. | Retry later; `details` carries the status and endpoint. |
| `upstream_unavailable` | The upstream could not be reached (network error or timeout). | Retry in a moment; call `edi_ping(check_api=true)`. |
| `result_too_large` | A result stayed above the hard size limit after trimming, or an upstream response exceeded the byte cap. | Narrow the request: a smaller `limit` or a narrower search. |
| `unknown_tool` | No tool has that name. | `details.available` lists the tools. |
| `internal_error` | A bug in edi-mcp. | Report it with the request id. |
| `feature_unavailable` | A download tool was called while downloads are disabled (`downloads.enabled: false`, or not stdio). | Use a stdio deployment with downloads enabled. |
| `not_available_in_http_mode` | Reserved; not raised today. Over HTTP the download tools are not listed, so calling one returns `unknown_tool`. | Use a stdio deployment. |
| `download_limit_exceeded` | A download plan or stream exceeds `downloads.max_files_per_call`, `max_bytes_per_call`, `max_file_bytes` or the call's `max_bytes`. | Download fewer entities, or raise the limit. |
| `download_denied` | A `dest_subdir` or file name outside the download directory, or a file that appeared while downloading. | Use a plain relative `dest_subdir`. |
| `checksum_mismatch` | Not raised as an error: a file whose SHA-1 differs from EDI's is removed and reported with status `failed` and this code in its `error` text. | Download it again. |

Results that are merely large are not errors: lists are trimmed to fit the result
budget (50,000 bytes by default) and report `page.truncatedReason: budget` with a
`nextOffset` to continue from.
