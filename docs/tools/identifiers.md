---
title: "Identifiers and scope names"
description: "How EDI packages are identified (scope.identifier.revision, DOIs, portal and PASTA URLs), which forms edi-mcp accepts, and how scope names and LTER site codes resolve."
type: Guide
tags:
  - tools
  - identifiers
  - scopes
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: pasta-api
    resource: "https://pasta.lternet.edu/package/docs/api"
    title: "EDI PASTA+ Data Package Manager REST API"
    author: "team:edi"
  - id: edi-doi
    resource: "https://edirepository.org/resources/citing-data"
    title: "EDI — Citing data"
    author: "team:edi"
status: stable
---

# Identifiers and scope names

## Anatomy of a package id

An EDI data package is identified by **scope.identifier.revision**:

| Part | Example | Meaning |
| --- | --- | --- |
| scope | `knb-lter-hbr`, `edi` | Namespace: `knb-lter-<site>` for each LTER site (hbr = Hubbard Brook, jrn = Jornada, ntl = North Temperate Lakes, …), `edi` for general EDI submissions, and others such as `msb-paleon` or `ecotrends`. |
| identifier | `14`, `210548103` | Integer, unique within the scope. |
| revision | `22` | Integer, incremented on every update. Older revisions stay available. Revisions can start at 0 (`msb-paleon.31.0`). |

`knb-lter-hbr.14.22` is revision 22 of package 14 in the Hubbard Brook scope; the
path form is `knb-lter-hbr/14/22`. `knb-lter-hbr.14` (no revision) is the package
*series*. `newest` and `oldest` stand for the latest and the first revision.

## Other identifiers

* **DOI.** Every revision has its own DOI, `doi:10.6073/pasta/<32 hex>`, resolvable
  at `https://doi.org/10.6073/pasta/<32 hex>`.
* **Landing page.**
  `https://portal.edirepository.org/nis/mapbrowse?scope=knb-lter-hbr&identifier=14&revision=22`
  (search results carry it as `portalUrl`).
* **Data entity.** A package's tables and files are *entities*, each with a 32-hex
  entity id (the MD5 of its EML `entityName`), addressed as
  `https://pasta.lternet.edu/package/data/eml/knb-lter-hbr/14/22/<entityId>`.
* **DataONE.** In DataONE the EML document's identifier is its PASTA metadata URL
  (`https://pasta.lternet.edu/package/metadata/eml/knb-lter-hbr/14/22`) and the
  package's resource map is its DOI.

## Forms edi-mcp accepts

Wherever a tool takes a package (today
[`edi_list_revisions`](reference.md#edi_list_revisions)), any of these work, and the
normalized id is echoed in `resolved` when it differs from the input:

* `knb-lter-hbr.14.22`, `knb-lter-hbr/14/22`, with an optional `.xml` suffix as in
  DataONE file names;
* `knb-lter-hbr.14`, `knb-lter-hbr.14.newest`, `knb-lter-hbr.14.oldest`;
* `doi:10.6073/pasta/…`, `10.6073/pasta/…`, `https://doi.org/10.6073/pasta/…`
  (also `dx.doi.org`);
* portal URLs: `…/nis/mapbrowse?scope=…&identifier=…&revision=…` or
  `…?packageid=scope.identifier.revision`;
* PASTA package, metadata and data URLs, also when URL-encoded inside a DataONE
  `/object/` or `/resolve/` URL;
* a site code or scope name in place of the scope: `jrn.210548103`,
  `Jornada Basin.210548103.33`.

A DOI outside `10.6073/pasta/` is rejected with `invalid_argument`: only EDI DOIs
identify EDI packages. A DOI is turned into a package id by the backend; with a key,
PASTA's search finds the newest revision's DOI and an older revision's DOI is looked
up in DataONE (the result's notes say so).

## Scope names and site codes

Scope arguments (`scope=` and the scope part of a package id) accept, in this order:

1. the **exact scope**: `knb-lter-jrn`, `edi`, `msb-cap`;
2. an **LTER site code**, any case: `JRN`, `hbr`. Three-letter codes always mean
   the LTER site, so `cap` is Central Arizona-Phoenix (`knb-lter-cap`); use
   `msb-cap` exactly for the Macrosystems scope;
3. a **name, alias or location**, scored alike: `Jornada`, `Hubbard Brook`,
   `Toolik`, `Kansas`;
4. a **hyphenated code** edi-mcp does not know passes through unchanged, so scopes
   newer than the snapshot still work with a key.

A name match is accepted when it is clear — a score of at least **0.75** and at least
**1.15 times** the runner-up — and is echoed in `resolved` with its confidence. A
name or location shared by several scopes returns `ambiguous_input` with ranked
`candidates` (`Alaska` matches four sites, `New Mexico` both Jornada and Sevilleta,
`Landsat` two bulk scopes); a name that matches nothing well returns `not_found`
with `didYouMean`.

Names, site codes and locations come from a dated snapshot of the repository's
scopes shipped with edi-mcp (`edi://reference/scopes`).
[`edi_list_scopes`](reference.md#edi_list_scopes) lists every scope, live from
PASTA when a key is set.
