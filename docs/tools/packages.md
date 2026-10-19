---
title: "Packages, metadata and entities"
description: "Inspect one EDI package revision with edi_get_package, read its EML metadata in compact sections with edi_get_metadata, and list its data tables and files with columns, formats and checksums with edi_list_entities."
type: Guide
tags:
  - tools
  - packages
  - EML
  - entities
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: pasta-api
    resource: "https://pasta.lternet.edu/package/docs/api"
    title: "EDI PASTA+ Data Package Manager REST API"
    author: "team:edi"
  - id: eml
    resource: "https://eml.ecoinformatics.org/"
    title: "Ecological Metadata Language (EML)"
    author: "team:nceas"
  - id: dataone-mn
    resource: "https://dataoneorg.github.io/api-documentation/apis/MN_APIs.html"
    title: "DataONE Member Node APIs"
    author: "team:dataone"
status: stable
---

# Packages, metadata and entities

Once a search or listing has named a package, three tools read it:
[`edi_get_package`](reference.md#edi_get_package) for an overview,
[`edi_get_metadata`](reference.md#edi_get_metadata) for the EML metadata, and
[`edi_list_entities`](reference.md#edi_list_entities) for the data tables and
files. All three take the same `package` and `revision` inputs, work on both
backends (PASTA with a key, DataONE without; see [Backends](backends.md)), and
fetch and parse the package's EML document once per call.

## Choosing a package and revision

`package` accepts every form described in [Identifiers and scope names](identifiers.md):
a full id (`knb-lter-hbr.14.22`), a series without a revision (`knb-lter-hbr.14`),
a DOI (`doi:10.6073/pasta/…`), a portal or PASTA URL, and a scope written as a site
code or name (`jrn.210548103`, `Jornada Basin.210548103`). When the package names
no revision, `revision` picks one: a number, `newest` (the default) or `oldest`.
Revision `0` is valid; some packages start there. Every result echoes the
normalised `packageId` and says in `revisionFrom` how the revision was chosen
(`given`, `newest`, `oldest` or `doi`).

## edi_get_package

The overview of one revision: `title`, `pubDate`, `creators` (names, with
`creatorsTotal`), `license`, `doi` and `doiUrl`, `portalUrl`, `metadataUrl`, and
`entities` with each entity's name, type and size, plus `entityCount` and
`totalBytes` across all entities.

- `newestRevision` and `isNewest` compare with the newest revision **on the backend
  that answered**. DataONE can lag PASTA, so without a key a note says that
  "newest" means DataONE's newest; PASTA may already hold a later revision.
- At most 100 entities are listed. A package with more says so in `notes` and
  `nextSteps` points at `edi_list_entities` with `offset=100` for the rest.
- `metadataUrl` is PASTA's EML URL, which needs an EDI API key to open.

## edi_get_metadata

The EML document projected into compact, capped sections. `include` picks the
sections (all by default):

| Section | Contents |
| --- | --- |
| `overview` | title, short name, abstract, keyword sets (with thesauri), publication date, language, alternate identifiers, maintenance |
| `people` | creators, contacts, associated parties and publisher, with roles, organisations, emails as published, and ORCIDs |
| `coverage` | geographic bounding boxes, temporal ranges and taxonomic coverage |
| `methods` | the method steps as prose, with the number of steps |
| `rights` | intellectual rights text and the structured license (name, URL, identifier) |
| `project` | project title, personnel, funding awards and related projects |
| `entities` | the data entities in summary form (use `edi_list_entities` for columns) |

`max_text_chars` (200–20000, default 2000) cuts the abstract, methods and rights
text; a cut field is flagged (for example `abstractTruncated`). Lists are capped
(25 people per list, 60 keywords, 50 taxa, 25 geographic and temporal ranges, …)
and every capped list reports its full count, such as `keywordsTotal`. EML
`<references>` to other elements are resolved, with a depth limit and a cycle guard.
Very large documents stay small: the largest EML tried, 3.4 MB with more than a
thousand taxa, projects to about 25 KB.

The raw EML is never returned inline.

## edi_list_entities

Every data entity (data table, spatial raster or vector, stored procedure, view or
other entity) with:

- name, entity type, object (file) name, description, format, byte size and record count;
- the text format of a delimited table: header and footer lines, field and record delimiters
  (as written in the EML, for example the literal `\r\n`), quote character and orientation;
- with `include_attributes` (default true), each column's name, label, definition,
  storage type, measurement scale, unit, date format, numeric bounds, code lists,
  missing-value codes and semantic annotations;
- with `include_checksums`, SHA-1 checksums fetched for up to 25 entities per call
  (one request per entity); without it, checksums appear only where the backend
  already supplied them;
- `dataUrl`, PASTA's data URL, which needs an EDI API key, and `anonymousUrl`, a
  DataONE member-node URL that serves the same bytes without a key. `anonymousUrl`
  is omitted for scopes that the server's dated snapshot shows DataONE does not
  replicate.

`entity` narrows the list to one entity by id, name or file name
(case-insensitive). `offset` and `limit` (default 50, at most 200) page through
large packages, and `page.nextOffset` gives the next page. If a page would exceed
the result budget, column lists are dropped first and `attributesElided` is set;
ask for fewer entities or one `entity` to get them back.

## Typical flow

1. `edi_search_packages` → pick a `packageId`.
2. `edi_get_package` → is it the newest revision, how many entities, how big?
3. `edi_get_metadata` with `include=["overview","coverage","methods"]` → is it the
   right data?
4. `edi_list_entities` with `entity=…` → which columns, units and missing-value
   codes, and where to fetch the file.

Previewing rows, downloading files and formatted citations come with the next
build step; see the [Roadmap](roadmap.md).
