---
title: "Backends: PASTA and DataONE"
description: "Why edi-mcp reads PASTA when an EDI API key is set and the anonymous DataONE replicas otherwise, how a result says which one answered, and the caveats of the DataONE fallback."
type: Explanation
tags:
  - tools
  - backends
  - pasta
  - dataone
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: edi-news-auth
    resource: "https://edirepository.org/news/news-20260727.00"
    title: "EDI news, 2026-07-27: authentication required for the PASTA API"
    author: "team:edi"
  - id: pasta-api
    resource: "https://pasta.lternet.edu/package/docs/api"
    title: "EDI PASTA+ Data Package Manager REST API"
    author: "team:edi"
  - id: dataone-api
    resource: "https://dataoneorg.github.io/api-documentation/"
    title: "DataONE API documentation"
    author: "team:dataone"
status: stable
---

# Backends: PASTA and DataONE

Since **2026-07-30** every request to EDI's PASTA+ REST API must be authenticated,
including reads of public data[^edi-news-auth]; an anonymous request gets HTTP 403
("Public Access … not authorized"). DataONE still serves EDI content anonymously, so
edi-mcp has two backends behind one contract:

| | PASTA | DataONE |
| --- | --- | --- |
| Used when | the call has an EDI API key | the call has no key |
| Search and listings | `pasta.lternet.edu/package/search/eml` and `/package/eml/…` | the coordinating node's Solr index, `cn.dataone.org/cn/v2/query/solr/` |
| EML and data | `pasta.lternet.edu/package/…` | the member node holding the scope (`gmn.edirepository.org` for `edi`, `gmn.lternet.edu` otherwise), then `cn.dataone.org` as a fallback |
| Freshness | authoritative | replicas; new uploads can take days to appear |

Each tool produces the same output model from either backend, and every result's
`source.backend` says which one answered: `pasta` or `dataone`, or `local` when
no upstream call was made. [`edi_ping`](reference.md#edi_ping) reports the backend that
serves the current caller.

## A bad key is an error, never a downgrade

If a key is configured and PASTA rejects it (HTTP 401), the tool fails with
`upstream_forbidden`; edi-mcp does **not** quietly retry on DataONE, because a silent
downgrade would hide the misconfiguration and change what the results mean. A 403
with valid credentials means the package is restricted to named users or groups; it
is also `upstream_forbidden`, with `reason: access_restricted`, and a new key will not
help. See [Utilities and errors](utilities.md#error-codes).

One deliberate exception keeps answers correct rather than changing their source:
PASTA's search indexes only the newest revision of each package, so a DOI of an
older revision is resolved through DataONE even with a key, and the result's notes
say so.

## Key-only operations

Some EDI services have no DataONE counterpart: provenance (lineage), the change
feed, read counts and whole-package zip downloads. Their tools
([`edi_get_lineage`](reference.md#edi_get_lineage),
[`edi_recent_changes`](reference.md#edi_recent_changes),
[`edi_get_read_counts`](reference.md#edi_get_read_counts) and
[`edi_download_package`](reference.md#edi_download_package)) return `auth_required`
without a key. Quality reports are the exception the original plan did not expect:
the member nodes serve PASTA's reports anonymously, so
[`edi_get_quality_report`](reference.md#edi_get_quality_report) works on both
backends. [`edi_list_scopes`](reference.md#edi_list_scopes) needs PASTA for a
live list and falls back to edi-mcp's dated scope snapshot without a key.

## Caveats of the DataONE fallback

* **Lag.** The DataONE index can trail new EDI uploads and new revisions by a day or
  more. Results served from DataONE carry a note saying so.
* **Coverage.** Not every EDI scope is replicated to DataONE;
  [`edi_list_scopes`](reference.md#edi_list_scopes) shows DataONE package counts from
  the snapshot, and a scope with none needs a key.
* **Revisions.** DataONE's obsolescence links are unreliable, so edi-mcp parses each
  record's revision from its identifier, keeps the highest revision per package,
  and reports search totals as an upper bound (`totalExact: false`).
* **Proxying.** The member nodes proxy PASTA, so EDI could restrict them in the same
  way it restricted PASTA.
* **Drift.** DataONE's index changes without notice: which scopes are replicated,
  which fields can be sorted, and the order of results for filter-only queries have
  all changed while edi-mcp was being built. Do not rely on DataONE's result order,
  and set a key when you need authoritative answers.

[^edi-news-auth]: EDI news, 2026-07-27. <https://edirepository.org/news/news-20260727.00>
