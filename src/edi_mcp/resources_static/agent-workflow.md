# edi-mcp agent workflow

A five-call path from a question to cited data. Every result is compact JSON with
`resolved`, `notes`, `nextSteps` and `source`; lists also carry `page`. Follow
`page.nextOffset` before concluding a list is complete, and read `notes`: they say
when DataONE served the call and may lag PASTA.

1. **Find packages:** `edi_search_packages(query="streamflow", scope="Hubbard Brook", start_year=1990)`.
   Returns the newest revision of each match with title, DOI, dates, creators and a
   portal link. Filters: `scope`, `author`, `start_year` / `end_year`, `bbox`
   (`[west, south, east, north]`), `sort` (relevance, newest, oldest). See
   `edi://guide/search-syntax`.
2. **Inspect one:** `edi_get_package(package="knb-lter-hbr.14")` for the DOI,
   entity count and sizes; `edi_get_metadata(package=..., include=["overview", "coverage", "methods"])`
   for the projected EML (sections: overview, people, coverage, methods, rights,
   project, entities).
3. **Pick a table:** `edi_list_entities(package=..., include_attributes=true)` lists
   each entity's id, name, file name, size, SHA-1, format and columns (name,
   definition, unit, type, missing-value codes).
4. **Look, then fetch:** `edi_preview_entity(package=..., entity="<id or name>", rows=20)`
   shows the first rows using the EML's delimiter and header layout.
   `edi_download_entities(package=..., entities=[...])` (stdio only) saves files
   under the download directory, verifies SHA-1 checksums and never overwrites a
   file. Over HTTP, give the user the entity URLs instead.
5. **Cite:** `edi_get_citation(package="knb-lter-hbr.14.22")` (style ESIP, DRYAD or
   BIBTEX). Cite the exact revision used, by its DOI; see `edi://guide/citing-edi-data`.

Also: `edi_get_quality_report` (EDI's congruence checks), `edi_list_revisions`,
`edi_list_scopes` / `edi_list_identifiers`, and, with a key only, `edi_get_lineage`,
`edi_recent_changes`, `edi_get_read_counts` and `edi_download_package` (the whole
package as one zip, which can be very large).

## Inputs

* `package` accepts `knb-lter-hbr.14.22`, `knb-lter-hbr.14` (newest unless `revision`
  is set), `knb-lter-hbr/14/22`, `doi:10.6073/pasta/<md5>`, doi.org links and portal or
  PASTA URLs. The normalized `packageId` is echoed in `resolved`. See
  `edi://guide/package-identifiers`.
* Scopes accept an exact scope (`knb-lter-jrn`), an LTER site code (`JRN`) or a name
  (`Jornada`); `edi://reference/scopes` lists them all.
* `entity` / `entities` accept an entity id, its name or its file name, any case.

## Keys and backends

Call `edi_ping` first. With `EDI_API_KEY` set (stdio) or an `X-EDI-Key` header
(HTTP), PASTA answers (`source.backend: pasta`). Without one, the anonymous DataONE
replicas answer (`dataone`): search can lag new uploads by days, `newest` means
DataONE's newest, scopes DataONE does not replicate need a key, and the key-only
tools return `auth_required`. See `edi://guide/api-key`.

## Errors (`structuredContent.error.code`)

| Code | Meaning | What to do |
|---|---|---|
| `auth_required` | The call needs an EDI API key | Read `edi://guide/api-key` |
| `upstream_forbidden` | EDI refused the key, or (`reason: access_restricted`) the package is restricted | Replace the key, or ask the package contact |
| `not_found` | No such package, revision, scope or entity | Check the id; use `didYouMean` |
| `ambiguous_input` | A scope name matched several scopes | Retry with one of `candidates` |
| `invalid_argument` | Bad or unknown argument | The message names the field |
| `rate_limited` | EDI's rate limit | Wait `retryAfterSeconds` |
| `result_too_large` / `download_limit_exceeded` | Request too wide | Narrow it, or pass fewer entities |
| `upstream_error` / `upstream_unavailable` | EDI or DataONE failed or is unreachable | Retry later; `edi_ping(check_api=true)` |
