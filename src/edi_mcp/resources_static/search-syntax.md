# Searching EDI packages

`edi_search_packages` sends the same typed filters to PASTA (with a key) or to the
DataONE index (without one). It returns the newest revision of each matching package.

## query

Free text over titles, keywords and abstracts, as Solr's edismax parser reads it:

* words: `streamflow chemistry` matches packages with **either** word (both backends
  combine words with OR; packages with more matches rank higher). Use `AND` or `+` to
  require every word: `streamflow AND chemistry`, `+streamflow +chemistry`
* phrases: `"net primary production"`
* operators: `nitrogen AND (stream OR river)`, `grassland NOT fire`; `+word` requires
  a word and `-word` excludes one

Omit `query` to browse with filters only. Raw Solr field syntax (`title:...`) is not a
supported part of the interface: the two backends index different fields, so use the
typed filters below instead.

## Filters

| Argument | Meaning |
|---|---|
| `scope` | One scope, LTER site code or name (`knb-lter-jrn`, `JRN`, `Jornada`); see `edi://reference/scopes` |
| `author` | A creator's last name, any case (`Likens`) |
| `start_year`, `end_year` | Temporal coverage overlaps the years: it reaches `start_year` or later and starts in `end_year` or earlier |
| `bbox` | `[west, south, east, north]` in decimal degrees; geographic coverage must intersect it. Split a box that crosses the antimeridian into two searches |
| `sort` | `relevance` (default), `newest`, `oldest` |
| `include_bulk` | Include the generated bulk scopes `ecotrends`, `lter-landsat` and `lter-landsat-ledaps` (about 36,000 records), left out of unscoped searches by default |
| `limit`, `offset` | Page size (1-50, default 10) and first result; follow `page.nextOffset` |

## PASTA and DataONE differences

* **Totals:** exact on PASTA. On DataONE `totalExact` is false: superseded revisions
  are collapsed to one hit per package, so `page.total` is an upper bound and a page
  can hold fewer than `limit` packages.
* **Freshness:** the DataONE index can lag new uploads by days.
* **Dates:** PASTA's publication date is a year, DataONE's a date. Without a key
  `newest` / `oldest` sort by the date each revision reached DataONE (`uploaded`).
* **Ranking:** relevance scores differ between the two indexes; do not compare them.

## Tips

* Start broad, then add `scope` or years; an empty result says so in `notes`.
* To walk a whole scope, use `edi_list_identifiers(scope=...)` instead of paging a
  search.
* A found package's `packageId` goes straight into `edi_get_package`,
  `edi_get_metadata` or `edi_list_entities`.
