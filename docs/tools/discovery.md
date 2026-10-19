---
title: "Discovery"
description: "Find EDI data packages with edi_search_packages and walk the repository hierarchy with edi_list_scopes, edi_list_identifiers and edi_list_revisions, on PASTA or DataONE."
type: Guide
tags:
  - tools
  - search
  - discovery
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: pasta-search
    resource: "https://pasta.lternet.edu/package/docs/api#GET%20:%20/search/eml"
    title: "PASTA+ Data Package Manager — search/eml"
    author: "team:edi"
  - id: dataone-solr
    resource: "https://dataoneorg.github.io/api-documentation/design/SearchMetadata.html"
    title: "DataONE Solr search metadata"
    author: "team:dataone"
status: stable
---

# Discovery

Four tools find packages and walk the repository's hierarchy of
**scope → identifier → revision**. All four work with or without an EDI API key:
with a key PASTA answers, without one the anonymous DataONE replicas do (see
[Backends](backends.md)). Every scope argument accepts an exact scope
(`knb-lter-jrn`), an LTER site code (`JRN`) or a name such as `Jornada`; see
[Identifiers and scope names](identifiers.md).

| Tool | Use it to |
| --- | --- |
| [`edi_search_packages`](reference.md#edi_search_packages) | find packages by text, scope, creator, years or bounding box |
| [`edi_list_scopes`](reference.md#edi_list_scopes) | see every scope with its name, kind, site code and package counts |
| [`edi_list_identifiers`](reference.md#edi_list_identifiers) | list the package identifiers in one scope |
| [`edi_list_revisions`](reference.md#edi_list_revisions) | list every revision of one package and find the newest |

## Search packages

`edi_search_packages` returns the **newest revision** of each matching package with
its title, DOI, publication date, temporal coverage, the first five creators
(`moreAuthors` counts the rest), the first ten keywords and an EDI Data Portal link.

| Input | Meaning |
| --- | --- |
| `query` | Free text over titles, keywords and abstracts: words, `"phrases"`, `AND` / `OR` / `NOT`. Omit it to browse with filters only. |
| `scope` | One scope, site code or scope name. |
| `author` | A creator's last name, any case (`Likens`). |
| `start_year`, `end_year` | Temporal overlap: coverage reaches `start_year` or later and starts in `end_year` or earlier. |
| `bbox` | `[west, south, east, north]` in decimal degrees; geographic coverage must intersect it. `west <= east`: split a box that crosses the antimeridian into two searches. |
| `sort` | `relevance` (default), `newest` or `oldest` by publication date (by DataONE upload date without a key). `oldest` lists undated packages first. |
| `include_bulk` | Include the generated bulk scopes `ecotrends`, `lter-landsat` and `lter-landsat-ledaps` (about 36,000 records), which are left out of unscoped searches by default. |
| `limit`, `offset` | Page size (1–50, default 10) and the index of the first result. |

Example: Hubbard Brook streamflow packages that cover the 1990s:

```json
{"query": "streamflow", "scope": "Hubbard Brook", "start_year": 1990, "end_year": 1999}
```

The scope name is resolved to `knb-lter-hbr` and echoed in `resolved` with its
confidence.

### PASTA and DataONE differences

The same filters are sent to both backends, but the two indexes are not identical:

* **Totals.** On PASTA `page.total` is exact. On DataONE `totalExact` is `false`:
  DataONE still counts some superseded revisions, which edi-mcp collapses to one hit
  per package, so `page.total` is an upper bound and a page can hold fewer than
  `limit` packages. A package can reappear on a later page at a higher revision.
* **Paging.** `page.nextOffset` advances by the rows requested (`offset + limit`),
  not by the hits kept, so no DataONE rows are read twice.
* **Freshness.** The DataONE index can lag new EDI uploads by days; results say so
  in `notes`.
* **Publication date.** PASTA returns a year, DataONE a date.
* **Date sorting.** Since 2026-10-19 DataONE refuses to sort on publication date,
  so without a key `sort=newest` and `sort=oldest` order results by the date each
  revision reached DataONE (`uploaded` on each hit), and a note says so. PASTA sorts
  by publication date.
* **Identifier forms.** DataONE returns some records under an older
  `scope.identifier.revision` id form; edi-mcp reads both and de-duplicates per
  package series.

## List scopes

`edi_list_scopes` lists the repository's scopes (`knb-lter-hbr`, `edi`, `msb-paleon`,
…) with name, `kind` (`lter`, `edi`, `bulk`, `project`, `agency`, `other`), LTER site
code, location and package counts on PASTA and DataONE. Filter with `kind`.

* **With a key** the scope list comes live from PASTA (`live: true`). Names and
  counts still come from edi-mcp's dated snapshot (`snapshotAsOf`); a scope newer
  than the snapshot has `kind: unknown`.
* **Without a key** DataONE has no scope listing, so the list is the snapshot
  itself (`live: false`), and scopes created since then are missing. The same
  snapshot is the `edi://reference/scopes` resource.

`dataonePackages: 0` means DataONE does not replicate that scope; reading it needs a
key.

## List identifiers

`edi_list_identifiers(scope=...)` lists a scope's numeric package identifiers in
ascending order, 200 per page by default (up to 1,000). A scope with no packages
returns `not_found`.

## List revisions

`edi_list_revisions(package=...)` lists every revision of one package, ascending,
with `newest`, `oldest` and `newestPackageId`. `package` accepts a series
(`knb-lter-hbr.14`), any revision (`knb-lter-hbr.14.22`), a DOI, or a portal or
PASTA URL, and the scope part may be a site code or name (`jrn.210548103`).
Revision numbers can start at 0.

Without a key the revisions come from DataONE, which can lag a new revision; edi-mcp
reads the revision from each record's identifier instead of DataONE's obsolescence
links, which are unreliable.

## Pagination

Search and identifier listings are paginated with `offset` and `limit`. Every page
reports `page.total` (when known), `returned`, `truncated` and `nextOffset`; when
`nextOffset` is set, the result's `nextSteps` include the call for the next page.
A result that would exceed the size budget is trimmed and reports
`truncatedReason: budget`.
