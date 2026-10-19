---
title: "EDI API key"
description: "Why EDI's PASTA+ API needs a key since 2026-07-30, how to create one, how to give it to edi-mcp as EDI_API_KEY, how to check that EDI accepts it, what works without a key, and the errors a missing or refused key produces."
type: Guide
tags:
  - getting-started
  - authentication
  - api-key
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: edi-news-20260727
    resource: "https://edirepository.org/news/news-20260727.00"
    title: "EDI news — authentication required for the PASTA API (2026-07-27)"
    author: "team:edi"
  - id: edi-access-keys
    resource: "https://edirepository.org/resources/working-with-access-keys"
    title: "EDI — Working with access keys"
    author: "team:edi"
  - id: edi-auth
    resource: "https://auth.edirepository.org/auth/ui/signin"
    title: "EDI authentication service"
    author: "team:edi"
  - id: api-key-guide
    resource: "https://github.com/idss-mesa/edi-mcp/blob/main/src/edi_mcp/resources_static/api-key.md"
    title: "edi-mcp guide edi://guide/api-key"
    author: "team:idss-mesa"
status: stable
stale_after: "2027-04-19T00:00:00Z"
---

# EDI API key

## Why a key

Since **2026-07-30** the EDI repository's PASTA+ REST API requires authentication for
every request, including reads of public data[^edi-news-20260727]. An anonymous request
is refused with HTTP 403 ("Public Access … not authorized"), or 401 from the audit
service. Keys are free.

edi-mcp is a hybrid: with a key it talks to PASTA; without one it reads the anonymous
DataONE replicas of EDI content (see [Backends](../tools/backends.md)). A key gives you
the authoritative, up-to-date repository and, once they are built, the operations only
PASTA offers. The server carries a short version of this page as the
`edi://guide/api-key` resource[^api-key-guide].

## Create a key

1. Sign in at [auth.edirepository.org](https://auth.edirepository.org/auth/ui/signin){target=_blank}[^edi-auth]
   with Google, Microsoft, GitHub or ORCID. A free EDI profile is created on first
   sign-in.
2. Open **Access Keys** from the avatar menu at the top right, or go straight to
   [auth.edirepository.org/auth/ui/key](https://auth.edirepository.org/auth/ui/key){target=_blank}.
3. Choose **New Key**, give it a name (for example `edi-mcp`), and set **Principal** to
   your own profile. A group principal limits the key to that group's access.
4. Copy the key.

EDI's own guide: [Working with access keys](https://edirepository.org/resources/working-with-access-keys){target=_blank}[^edi-access-keys].

## Give it to edi-mcp

- **stdio (Claude Code, Claude Desktop, …):** set `EDI_API_KEY` in the server's
  environment, for example
  `claude mcp add edi -s user -e EDI_API_KEY="$EDI_API_KEY" -- edi-mcp --transport stdio`
  ([Clients](clients.md) has every client). `EDI_MCP_EDI__API_KEY`, when set, takes
  precedence.
- **HTTP deployments:** each caller sends their own key in the `X-EDI-Key` header. It is
  honoured only when the server's `public_base_url` is `https://`. The operator's key is
  not lent to callers unless `share_config_key_over_http` is enabled, and the MCP
  `Authorization` header is never forwarded to EDI. See
  [Hosted HTTP deployment](../deploy/hosted-http.md).

There is deliberately **no command-line flag** for the key: arguments show up in `ps`
output and shell history. edi-mcp does not load `.env` files itself, and it ignores
look-alike names such as `EDI_KEY`, `EDI_TOKEN` and `EDI_AUTH_TOKEN` (it logs a warning
when one of them is set without `EDI_API_KEY`).

edi-mcp exchanges the key for a short-lived `edi-token` (8 hours) at
`auth.edirepository.org`, keeps it in memory only, renews it before it expires, and
sends it to PASTA as a cookie. If the authentication service is unavailable it falls
back to passing the key as a query parameter to PASTA. The key and the token go only to
EDI hosts and never appear in results, logs or errors; every URL edi-mcp reports is
scrubbed first.

## Check the key

`edi-mcp --check` only reports whether a key is configured (`keyConfigured`) and which
backend that selects; it makes no network request. To confirm that EDI accepts the key,
ask your agent to call `edi_ping` with `check_api=true`. The `api` block of the result
shows `reachable: true` and `credential: "token"` (or `"key"` when the query-parameter
fallback was used). A refused key shows up as an `error` with code
`upstream_forbidden`.

## Without a key

Without a key, edi-mcp answers from DataONE. The tools available today all work that
way; several planned tools will need a key.

| Operation | Without a key (DataONE) | With a key (PASTA) |
| --- | --- | --- |
| Search (`edi_search_packages`) | yes | yes |
| Scope list (`edi_list_scopes`) | dated snapshot | live |
| Identifiers and revisions (`edi_list_identifiers`, `edi_list_revisions`) | yes | yes |
| Package metadata and data entities *(planned)* | yes | yes |
| Data preview and download *(planned)* | yes | yes |
| Citations *(planned; cite.edirepository.org)* | yes | yes |
| Quality reports, lineage, change feeds, read counts *(planned)* | no | yes |
| Whole-package zip download *(planned)* | no | yes |

See the [Roadmap](../tools/roadmap.md) for the planned tools.

Caveats of the fallback: the DataONE index can lag new EDI uploads by a day or more and
may not hold every scope or revision PASTA has; the DataONE member nodes proxy PASTA, so
EDI could restrict them too. `source.backend` in every result says which backend
answered.

## Errors

- `auth_required`: the operation needs a key and none is configured for this call. The
  error points at the `edi://guide/api-key` resource.
- `upstream_forbidden`: a key was sent and EDI refused the request.
    - Without a `reason` (HTTP 401): EDI rejected the key (mistyped, expired, deleted, or
      a group key without access). Fix or replace the key.
    - With `reason: access_restricted` (HTTP 403): the key works, but this package is
      restricted to named users or groups. A new key will not help; ask the package's
      contact for access or pick another package.

edi-mcp never silently falls back to DataONE in either case: a bad key is an error, not
a downgrade.

[^edi-news-20260727]: EDI news, 2026-07-27. <https://edirepository.org/news/news-20260727.00>
[^edi-auth]: EDI authentication service. <https://auth.edirepository.org/auth/ui/signin>
[^edi-access-keys]: EDI — Working with access keys. <https://edirepository.org/resources/working-with-access-keys>
[^api-key-guide]: edi-mcp guide `edi://guide/api-key`. <https://github.com/idss-mesa/edi-mcp/blob/main/src/edi_mcp/resources_static/api-key.md>
