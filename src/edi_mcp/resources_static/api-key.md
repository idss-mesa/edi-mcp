# EDI API key

## Why a key

Since **2026-07-30** the EDI repository's PASTA REST API requires authentication for
every request, including reads of public data
([EDI announcement](https://edirepository.org/news/news-20260727.00)). An anonymous
request is refused with HTTP 403 ("Public Access … not authorized"), or 401 from the
audit service.

## Create a key

1. Sign in at <https://auth.edirepository.org/auth/ui/signin> with Google, Microsoft,
   GitHub or ORCID. A free EDI profile is created on first sign-in.
2. Open **Access Keys** from the avatar menu at the top right, or go straight to
   <https://auth.edirepository.org/auth/ui/key>.
3. Choose **New Key**, give it a name (e.g. `edi-mcp`), and set **Principal** to your
   own profile. A group principal limits the key to that group's access.
4. Copy the key.

EDI's guide: <https://edirepository.org/resources/working-with-access-keys>.

## Give it to edi-mcp

- **stdio (Claude Code, Claude Desktop, …):** set `EDI_API_KEY` in the server's
  environment, e.g. `claude mcp add edi -e EDI_API_KEY=… -- uvx edi-mcp`.
  `EDI_MCP_EDI__API_KEY` overrides it. edi-mcp does not read `.env` files on its own,
  has no key flag (command lines leak into `ps` and shell history), and ignores
  look-alike names such as `EDI_TOKEN`.
- **HTTP deployments:** each caller sends its own key in the `X-EDI-Key` header. It
  is honoured only when the server's `public_base_url` is `https://`. The operator's
  key is not lent to callers unless `share_config_key_over_http` is enabled. The MCP
  `Authorization` header is never forwarded to EDI.

edi-mcp exchanges the key for a short-lived `edi-token` (8 hours) at
`auth.edirepository.org`, keeps it in memory only, renews it before it expires, and
sends it to PASTA as a cookie. The key never appears in results, logs or errors.

## Without a key

edi-mcp falls back to the anonymous DataONE replicas of EDI content:

| Works without a key | Needs a key |
|---|---|
| Search (DataONE index) | Quality reports |
| Package metadata (EML) | Provenance / lineage |
| Data entities: list, preview, download | Change and upload feeds |
| Citations (cite.edirepository.org) | Read counts |
| | Whole-package zip download |

Caveats of the fallback: the DataONE index can lag new EDI uploads by a day or more and
misses some revisions (its newest revision of a package can be older than PASTA's), a few
scopes are not replicated, and the DataONE member nodes proxy PASTA, so EDI could restrict
them too. `source.backend` in every result says which backend answered.

Data URLs: each entity from `edi_list_entities` has a `dataUrl` on PASTA, which needs a
key, and an `anonymousUrl` on its DataONE member node, which does not.

## Errors

- `auth_required`: the operation needs a key and none is configured for this call.
- `upstream_forbidden`: a key was sent and EDI refused the request.
  - Without a `reason` (HTTP 401): EDI rejected the key (mistyped, expired, deleted, or a
    group key without access). Fix or replace the key.
  - With `reason: access_restricted` (HTTP 403): the key works, but this package is
    restricted to named users or groups. A new key will not help; ask the package's
    contact for access or pick another package.

  edi-mcp never silently falls back to DataONE in either case.
