---
title: "Tool reference"
description: "Every edi-mcp tool with its inputs, result fields, upstream endpoints, key requirement and annotations, generated from the registry."
type: MCP Tool Reference
tags:
  - tools
  - reference
  - generated
generated:
  by: "process:gen_tools_reference"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: registry
    resource: "https://github.com/idss-mesa/edi-mcp/tree/main/src/edi_mcp/tools"
    title: "edi-mcp tool registry"
    author: "team:idss-mesa"
  - id: pasta-api
    resource: "https://pasta.lternet.edu/package/docs/api"
    title: "EDI PASTA+ Data Package Manager REST API"
    author: "team:edi"
status: stable
---

# Tool reference

Generated from the tool registry by `scripts/gen_tools_reference.py`; do not edit by hand. 16 tools are registered; `edi_download_entities`, `edi_download_package` are offered only over stdio. Inputs are snake_case and outputs camelCase. Every result also carries `resolved`, `notes`, `nextSteps` and `source` (whose `backend` says whether PASTA or DataONE answered), and failures return `structuredContent.error` with a stable `code` (see [Utilities](utilities.md#error-codes)).

| Tool | Title | Family | EDI API key |
| --- | --- | --- | --- |
| [`edi_download_entities`](#edi_download_entities) | Download data entities | [data](data.md) | no |
| [`edi_download_package`](#edi_download_package) | Download a whole package (zip) | [data](data.md) | required |
| [`edi_get_citation`](#edi_get_citation) | Cite an EDI data package | [citation](citation-and-quality.md) | no |
| [`edi_get_lineage`](#edi_get_lineage) | Get a package's provenance | [provenance](citation-and-quality.md) | required |
| [`edi_get_metadata`](#edi_get_metadata) | Read a package's EML metadata | [packages](packages.md) | no |
| [`edi_get_package`](#edi_get_package) | Get an EDI data package | [packages](packages.md) | no |
| [`edi_get_quality_report`](#edi_get_quality_report) | Get a package's quality report | [provenance](citation-and-quality.md) | no |
| [`edi_get_read_counts`](#edi_get_read_counts) | Get a package's read counts | [feeds](feeds.md) | required |
| [`edi_list_entities`](#edi_list_entities) | List a package's data entities | [entities](packages.md) | no |
| [`edi_list_identifiers`](#edi_list_identifiers) | List package identifiers in a scope | [discovery](discovery.md) | no |
| [`edi_list_revisions`](#edi_list_revisions) | List the revisions of a package | [discovery](discovery.md) | no |
| [`edi_list_scopes`](#edi_list_scopes) | List EDI scopes | [discovery](discovery.md) | no |
| [`edi_ping`](#edi_ping) | Check edi-mcp status | [core](utilities.md) | no |
| [`edi_preview_entity`](#edi_preview_entity) | Preview a data entity | [data](data.md) | no |
| [`edi_recent_changes`](#edi_recent_changes) | List recent repository changes | [feeds](feeds.md) | required |
| [`edi_search_packages`](#edi_search_packages) | Search EDI data packages | [discovery](discovery.md) | no |

## edi_download_entities

**Download data entities.** Save a package's data entities (all, or the ones named) and its EML into the configured download directory (stdio only). The plan is checked against file and byte caps first; SHA-1 checksums are verified; existing identical files are skipped and different ones are never overwritten. Works with or without a key. Next: read the files (pandas.read_csv) and cite with edi_get_citation.

| | |
| --- | --- |
| Surface | `data` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | stdio |
| Annotations | readOnly=false, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/metadata/eml/{scope}/{id}/{rev}`<br>`GET pasta.lternet.edu/package/data/eml/{scope}/{id}/{rev}/{entity}`<br>`GET pasta.lternet.edu/package/data/checksum/eml/{scope}/{id}/{rev}/{entity}`<br>`GET gmn.lternet.edu/mn/v2/object/{pid}`<br>`GET gmn.lternet.edu/mn/v2/meta/{pid}` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A package: knb-lter-hbr.14.22, knb-lter-hbr.14 (newest unless revision is set), a DOI, or a portal or PASTA URL; the scope may be a site code or name (jrn.210548103). (min length 1; max length 500) |
| `revision` | integer \\| `newest` \\| `oldest` \\| null |  | null | Revision when package names none: a number, 'newest' (default) or 'oldest'. |
| `entities` | array of string \\| null |  | null | Entity ids, names or file names; all when omitted. (max items 200) |
| `include_metadata` | boolean |  | true | Also save the EML as <packageId>.xml. |
| `dest_subdir` | string \\| null |  | null | Sub-directory of the download directory. (max length 200) |
| `max_bytes` | integer \\| null |  | null | Refuse plans larger than this. (>= 1) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `packageId` | string |  |
| `directory` | string | Where the files were saved. |
| `files` | array of SavedFile |  |
| `downloaded` | integer |  |
| `bytes` | integer | Bytes transferred by this call. |

## edi_download_package

**Download a whole package (zip).** Save one package revision as PASTA's zip archive (metadata, data entities, quality report) into the configured download directory (stdio only; needs an EDI API key). Archives can be very large: the transfer stops at the byte cap, and an existing file is never overwritten. Next: unzip it, or prefer edi_download_entities for chosen files.

| | |
| --- | --- |
| Surface | `data` |
| EDI API key | required |
| Transports | stdio |
| Annotations | readOnly=false, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/download/eml/{scope}/{id}/{rev}` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A package: knb-lter-hbr.14.22, knb-lter-hbr.14 (newest unless revision is set), a DOI, or a portal or PASTA URL; the scope may be a site code or name (jrn.210548103). (min length 1; max length 500) |
| `revision` | integer \\| `newest` \\| `oldest` \\| null |  | null | Revision when package names none: a number, 'newest' (default) or 'oldest'. |
| `dest_subdir` | string \\| null |  | null | Sub-directory of the download directory. (max length 200) |
| `max_bytes` | integer \\| null |  | null | Stop and fail beyond this many bytes. (>= 1) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `packageId` | string |  |
| `directory` | string | Where the files were saved. |
| `files` | array of SavedFile |  |
| `downloaded` | integer |  |
| `bytes` | integer | Bytes transferred by this call. |

## edi_get_citation

**Cite an EDI data package.** A formatted citation for one package revision from the EDI citation service: ESIP (default), DRYAD or BibTeX, plus its parts (authors, year, title, version, publisher, DOI). Needs no key, though a key lets 'newest' come from PASTA. Restricted packages have no citation. Next: cite the DOI in your work and check the license with edi_get_metadata include=['rights'].

| | |
| --- | --- |
| Surface | `citation` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET cite.edirepository.org/cite/{packageId}`<br>`GET pasta.lternet.edu/package/eml/{scope}/{id}`<br>`GET cn.dataone.org/cn/v2/query/solr/` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A package: knb-lter-hbr.14.22, knb-lter-hbr.14 (newest unless revision is set), a DOI, or a portal or PASTA URL; the scope may be a site code or name (jrn.210548103). (min length 1; max length 500) |
| `revision` | integer \\| `newest` \\| `oldest` \\| null |  | null | Revision when package names none: a number, 'newest' (default) or 'oldest'. |
| `style` | `ESIP` \\| `DRYAD` \\| `BIBTEX` |  | `"ESIP"` | ESIP (default), DRYAD or BIBTEX. |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `packageId` | string |  |
| `revisionFrom` | `given` \\| `newest` \\| `oldest` \\| `doi` |  |
| `style` | `ESIP` \\| `DRYAD` \\| `BIBTEX` |  |
| `citation` | string | The formatted citation (BibTeX entry for BIBTEX). |
| `parts` | CitationParts |  |
| `doiUrl` | string \\| null |  |
| `portalUrl` | string |  |

## edi_get_lineage

**Get a package's provenance.** Provenance of one package revision: the EDI packages it was derived from (sources named in its EML methods) and the packages that name it as a source (descendants), with titles. Needs an EDI API key. Next: call edi_get_package on a source or descendant.

| | |
| --- | --- |
| Surface | `provenance` |
| EDI API key | required |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/sources/eml/{scope}/{id}/{rev}`<br>`GET pasta.lternet.edu/package/descendants/eml/{scope}/{id}/{rev}` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A package: knb-lter-hbr.14.22, knb-lter-hbr.14 (newest unless revision is set), a DOI, or a portal or PASTA URL; the scope may be a site code or name (jrn.210548103). (min length 1; max length 500) |
| `revision` | integer \\| `newest` \\| `oldest` \\| null |  | null | Revision when package names none: a number, 'newest' (default) or 'oldest'. |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `packageId` | string |  |
| `revisionFrom` | `given` \\| `newest` \\| `oldest` \\| `doi` |  |
| `sources` | array of LinkedOut | Packages this one was derived from. |
| `descendants` | array of LinkedOut | Packages derived from this one. |

## edi_get_metadata

**Read a package's EML metadata.** The package's EML, projected to compact sections: overview (abstract, keywords, dates), people (creators, contacts with ORCIDs), coverage (bounding boxes, date ranges, taxa), methods, rights and license, project and funding, and entities. Choose sections with include; long text is cut at max_text_chars and lists are capped with totals. Next: call edi_list_entities for column definitions, units and codes.

| | |
| --- | --- |
| Surface | `packages` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/metadata/eml/{scope}/{id}/{rev}`<br>`GET gmn.lternet.edu/mn/v2/object/{pid}`<br>`GET pasta.lternet.edu/package/eml/{scope}/{id}`<br>`GET cn.dataone.org/cn/v2/query/solr/` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A package: knb-lter-hbr.14.22, knb-lter-hbr.14 (newest unless revision is set), a DOI, or a portal or PASTA URL; the scope may be a site code or name (jrn.210548103). (min length 1; max length 500) |
| `revision` | integer \\| `newest` \\| `oldest` \\| null |  | null | Revision when package names none: a number, 'newest' (default) or 'oldest'. |
| `include` | array of `overview` \\| `people` \\| `coverage` \\| `methods` \\| `rights` \\| `project` \\| `entities` |  |  | Sections to return: overview (abstract, keywords, dates), people, coverage (geographic, temporal, taxonomic), methods, rights, project (funding), entities. Default: all. (min items 1) |
| `max_text_chars` | integer |  | `2000` | Cut abstract, methods and rights to this length. (>= 200; <= 20000) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `packageId` | string |  |
| `revisionFrom` | `given` \\| `newest` \\| `oldest` \\| `doi` |  |
| `emlVersion` | string \\| null |  |
| `title` | string \\| null |  |
| `shortName` | string \\| null |  |
| `abstract` | string \\| null |  |
| `abstractTruncated` | boolean \\| null |  |
| `keywords` | array of KeywordSet \\| null |  |
| `keywordsTotal` | integer \\| null |  |
| `pubDate` | string \\| null |  |
| `language` | string \\| null |  |
| `alternateIdentifiers` | array of string \\| null |  |
| `maintenance` | string \\| null |  |
| `creators` | array of Person \\| null |  |
| `creatorsTotal` | integer \\| null |  |
| `contacts` | array of Person \\| null |  |
| `associatedParties` | array of Person \\| null |  |
| `publisher` | Person \\| null |  |
| `coverage` | Coverage \\| null |  |
| `methods` | Methods \\| null |  |
| `license` | License \\| null |  |
| `project` | Project \\| null |  |
| `entities` | array of EntitySummary \\| null |  |
| `entitiesTotal` | integer \\| null |  |

## edi_get_package

**Get an EDI data package.** Overview of one package revision: title, publication date, creators, license, DOI, portal and metadata URLs, whether it is the newest revision, and its data entities with sizes and the total. Accepts package ids, series (newest unless revision is set), DOIs, portal or PASTA URLs, and site codes or scope names for the scope. Next: call edi_get_metadata for the full description or edi_list_entities for columns.

| | |
| --- | --- |
| Surface | `packages` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/metadata/eml/{scope}/{id}/{rev}`<br>`GET pasta.lternet.edu/package/name/eml/{scope}/{id}/{rev}`<br>`GET pasta.lternet.edu/package/data/size/eml/{scope}/{id}/{rev}`<br>`GET pasta.lternet.edu/package/doi/eml/{scope}/{id}/{rev}`<br>`GET pasta.lternet.edu/package/eml/{scope}/{id}`<br>`GET gmn.lternet.edu/mn/v2/object/{pid}`<br>`GET cn.dataone.org/cn/v2/query/solr/`<br>`GET cite.edirepository.org/cite/{packageId}` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A package: knb-lter-hbr.14.22, knb-lter-hbr.14 (newest unless revision is set), a DOI, or a portal or PASTA URL; the scope may be a site code or name (jrn.210548103). (min length 1; max length 500) |
| `revision` | integer \\| `newest` \\| `oldest` \\| null |  | null | Revision when package names none: a number, 'newest' (default) or 'oldest'. |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `packageId` | string |  |
| `series` | string | scope.identifier |
| `revision` | integer |  |
| `revisionFrom` | `given` \\| `newest` \\| `oldest` \\| `doi` | How the revision was chosen: given, newest, oldest, or the DOI's. |
| `newestRevision` | integer \\| null | Newest revision on the serving backend (DataONE can lag PASTA). |
| `isNewest` | boolean \\| null | revision == newestRevision. |
| `title` | string \\| null |  |
| `pubDate` | string \\| null |  |
| `doi` | string \\| null |  |
| `doiUrl` | string \\| null |  |
| `portalUrl` | string |  |
| `metadataUrl` | string | PASTA EML URL (needs an EDI API key). |
| `creators` | array of string |  |
| `creatorsTotal` | integer |  |
| `license` | License \\| null |  |
| `entityCount` | integer | All entities, including any not listed below. |
| `totalBytes` | integer \\| null | Sum of known entity sizes (all entities). |
| `entities` | array of EntitySummary | The first 100; edi_list_entities pages through all. |

## edi_get_quality_report

**Get a package's quality report.** PASTA's quality report for one package revision: how many congruence checks passed, warned or failed (metadata, and each data entity against its EML), and the details of every non-valid check with EDI's explanation and suggestion. Works with a key (PASTA) or without (DataONE member node). Next: inspect a flagged entity with edi_list_entities or edi_preview_entity.

| | |
| --- | --- |
| Surface | `provenance` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/report/eml/{scope}/{id}/{rev}`<br>`GET gmn.lternet.edu/mn/v2/object/{pid}` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A package: knb-lter-hbr.14.22, knb-lter-hbr.14 (newest unless revision is set), a DOI, or a portal or PASTA URL; the scope may be a site code or name (jrn.210548103). (min length 1; max length 500) |
| `revision` | integer \\| `newest` \\| `oldest` \\| null |  | null | Revision when package names none: a number, 'newest' (default) or 'oldest'. |
| `include_info` | boolean |  | false | Also list 'info' checks, not only warn/error. |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `packageId` | string |  |
| `revisionFrom` | `given` \\| `newest` \\| `oldest` \\| `doi` |  |
| `created` | string \\| null |  |
| `counts` | StatusCounts | Checks by status, dataset and entities together. |
| `issues` | array of QualityIssue | Non-valid checks, errors first. |
| `issuesTotal` | integer |  |
| `entities` | array of EntityQuality |  |
| `entitiesTotal` | integer |  |

## edi_get_read_counts

**Get a package's read counts.** How often a package series or one revision has been read on PASTA: totals and non-robot reads by resource type (package, metadata, quality report, data entities, zip archive) and per revision. Needs an EDI API key. Next: cite the package with edi_get_citation.

| | |
| --- | --- |
| Surface | `feeds` |
| EDI API key | required |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/audit/reads/{scope}/{id}[/{rev}]` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A series (knb-lter-hbr.14) for every revision, or one revision (knb-lter-hbr.14.22); the scope may be a site code or name. (min length 1; max length 500) |
| `revision` | integer \\| null |  | null | Only this revision of a series. (>= 0) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `series` | string |  |
| `revision` | integer \\| null |  |
| `totals` | object of ReadTally | By resource type: dataPackage, metadata, report, data, archive. |
| `revisions` | array of RevisionReads | Newest first (at most 100). |
| `revisionsTotal` | integer |  |

## edi_list_entities

**List a package's data entities.** Every data entity (table or file) of one package revision: name, type, file name, format, byte size, record count, CSV layout and the columns with definitions, storage types, units, date formats, code lists and missing-value codes; optional SHA-1 checksums. Gives the PASTA data URL and a DataONE URL readable without a key. Next: call edi_preview_entity or edi_download_entities with an entityId.

| | |
| --- | --- |
| Surface | `entities` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/metadata/eml/{scope}/{id}/{rev}`<br>`GET pasta.lternet.edu/package/name/eml/{scope}/{id}/{rev}`<br>`GET pasta.lternet.edu/package/data/size/eml/{scope}/{id}/{rev}`<br>`GET pasta.lternet.edu/package/data/checksum/eml/{scope}/{id}/{rev}/{entity}`<br>`GET gmn.lternet.edu/mn/v2/object/{pid}`<br>`GET gmn.lternet.edu/mn/v2/meta/{pid}`<br>`GET cn.dataone.org/cn/v2/query/solr/` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A package: knb-lter-hbr.14.22, knb-lter-hbr.14 (newest unless revision is set), a DOI, or a portal or PASTA URL; the scope may be a site code or name (jrn.210548103). (min length 1; max length 500) |
| `revision` | integer \\| `newest` \\| `oldest` \\| null |  | null | Revision when package names none: a number, 'newest' (default) or 'oldest'. |
| `entity` | string \\| null |  | null | Only this entity: its id, name or file name (case-insensitive). (max length 300) |
| `include_attributes` | boolean |  | true | Return each entity's columns (definitions, units, codes). |
| `include_checksums` | boolean |  | false | Fetch missing SHA-1 checksums (one request per entity, at most 25). |
| `limit` | integer |  | `50` | Entities per page (1-200). (>= 1; <= 200) |
| `offset` | integer |  | `0` | Index of the first entity (paging). (>= 0) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `packageId` | string |  |
| `revisionFrom` | `given` \\| `newest` \\| `oldest` \\| `doi` |  |
| `entities` | array of EntityDetail |  |
| `page` | Page |  |
| `attributesElided` | boolean \\| null | True when some entities' attributes were dropped to fit the budget. |

## edi_list_identifiers

**List package identifiers in a scope.** List the package identifiers in one scope, ascending and paginated (offset/limit). The scope may be exact (knb-lter-hbr), an LTER site code (HBR) or a name ('Hubbard Brook'). Identifiers are numbers; a package is scope.identifier.revision. Next: call edi_list_revisions(package='scope.identifier') for one identifier's revisions.

| | |
| --- | --- |
| Surface | `discovery` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/eml/{scope}`<br>`GET cn.dataone.org/cn/v2/query/solr/` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `scope` | string | yes |  | A scope (knb-lter-jrn), LTER site code (JRN) or scope name or location ('Jornada', 'Hubbard Brook'); see edi_list_scopes. (min length 1; max length 100) |
| `limit` | integer |  | `200` | Identifiers per page (1-1000). (>= 1; <= 1000) |
| `offset` | integer |  | `0` | Index of the first identifier (paging). (>= 0) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `scope` | string |  |
| `identifiers` | array of integer | Package identifiers in ascending order. |
| `page` | Page |  |

## edi_list_revisions

**List the revisions of a package.** List every revision of one data package (scope.identifier), ascending, with the newest and oldest. Accepts a series (knb-lter-hbr.14), any revision, a DOI, a portal or PASTA URL, and site codes or scope names in place of the scope. Without an API key DataONE answers and can lag new revisions. Next: call edi_get_package(package=newestPackageId).

| | |
| --- | --- |
| Surface | `discovery` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/eml/{scope}/{identifier}`<br>`GET pasta.lternet.edu/package/search/eml`<br>`GET cn.dataone.org/cn/v2/query/solr/`<br>`GET cn.dataone.org/cn/v2/object/{pid}` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A package series or any revision of it: knb-lter-hbr.14, knb-lter-hbr.14.22, knb-lter-hbr/14, a DOI, a portal or PASTA URL; the scope may be a site code or name (jrn.210548103). (min length 1; max length 500) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `series` | string | scope.identifier |
| `scope` | string |  |
| `identifier` | integer |  |
| `revisions` | array of integer | Every revision, ascending. |
| `newest` | integer |  |
| `oldest` | integer |  |
| `newestPackageId` | string |  |

## edi_list_scopes

**List EDI scopes.** List the repository's scopes (knb-lter-hbr, edi, ...) with name, kind, LTER site code, location and package counts on PASTA and DataONE. With an API key the list comes live from PASTA; without one it is edi-mcp's dated snapshot (also edi://reference/scopes). Scope arguments elsewhere also accept these site codes and names. Next: call edi_search_packages(scope=...) or edi_list_identifiers(scope=...).

| | |
| --- | --- |
| Surface | `discovery` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/eml` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `kind` | `lter` \\| `edi` \\| `bulk` \\| `project` \\| `agency` \\| `other` \\| null |  | null | Only one kind: lter (LTER sites), edi (general EDI submissions), bulk (generated; excluded from search by default), project, agency or other. |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `scopes` | array of ScopeInfo |  |
| `page` | Page |  |
| `live` | boolean | True when PASTA listed the scopes just now; false = edi-mcp's snapshot. |
| `snapshotAsOf` | string | Date of the snapshot that supplies names and counts. |

## edi_ping

**Check edi-mcp status.** Liveness and capability report: server version and protocol, whether an EDI API key is available and therefore which backend serves this caller (pasta with a key, dataone without), which tools need a key, and whether downloads are enabled. Never reveals the key. With check_api=true it also makes one small request to that backend to confirm the key and connectivity. Next: call edi_search_packages to find data packages.

| | |
| --- | --- |
| Surface | `core` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/eml`<br>`GET cn.dataone.org/cn/v2/query/solr/` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `check_api` | boolean |  | false | Also make one small request to the backend serving this caller (with a key: exchange it for a token and list PASTA scopes; without: one DataONE query). |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `pong` | `ok` |  |
| `version` | string |  |
| `protocolVersion` | string |  |
| `transport` | `stdio` \\| `http` |  |
| `keyConfigured` | boolean | True when this call has an EDI API key available (never the key itself). |
| `keySource` | `config` \\| `request` \\| `none` |  |
| `backend` | `pasta` \\| `dataone` | Backend serving this caller: pasta with a key, dataone without one. |
| `keyRequiredTools` | array of string | Registered tools that need a key and fail with auth_required without one. |
| `downloadsEnabled` | boolean |  |
| `downloadDir` | string \\| null |  |
| `endpoints` | Endpoints |  |
| `api` | ApiCheck \\| null | Present when check_api was requested. |

## edi_preview_entity

**Preview a data entity.** The first rows of one delimited data entity (a CSV or other text table), parsed with the EML's delimiter, quote character and header lines, with column names. Reads at most a few hundred KB and stops; works with or without a key (PASTA or the DataONE member node). Binary entities are refused. Next: call edi_list_entities for column definitions and units, or edi_download_entities for the whole file.

| | |
| --- | --- |
| Surface | `data` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/metadata/eml/{scope}/{id}/{rev}`<br>`GET pasta.lternet.edu/package/data/eml/{scope}/{id}/{rev}/{entity}`<br>`GET gmn.lternet.edu/mn/v2/object/{pid}` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `package` | string | yes |  | A package: knb-lter-hbr.14.22, knb-lter-hbr.14 (newest unless revision is set), a DOI, or a portal or PASTA URL; the scope may be a site code or name (jrn.210548103). (min length 1; max length 500) |
| `revision` | integer \\| `newest` \\| `oldest` \\| null |  | null | Revision when package names none: a number, 'newest' (default) or 'oldest'. |
| `entity` | string | yes |  | Entity id, name or file name (case-insensitive). (min length 1; max length 300) |
| `rows` | integer |  | `20` | Data rows to return. (>= 1; <= 200) |
| `max_bytes` | integer \\| null |  | null | Most bytes to read (capped by limits.preview_max_bytes). (>= 1024) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `packageId` | string |  |
| `revisionFrom` | `given` \\| `newest` \\| `oldest` \\| `doi` |  |
| `entityId` | string \\| null |  |
| `name` | string \\| null |  |
| `size` | integer \\| null | Entity bytes, when known. |
| `columns` | array of string | Column names (file header, else EML attributes). |
| `columnsFrom` | `header` \\| `eml` \\| `none` |  |
| `rows` | array of array of string | Data rows as text; long cells end with '…'. |
| `complete` | boolean | True when every row of the entity is shown. |
| `bytesRead` | integer |  |

## edi_recent_changes

**List recent repository changes.** Packages inserted, updated (new revisions) or deleted in PASTA during a date window (default the last 7 days, at most 92), optionally for one scope or kind, newest first, with DOIs. Needs an EDI API key. Next: call edi_get_package on a packageId.

| | |
| --- | --- |
| Surface | `feeds` |
| EDI API key | required |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/changes/eml` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `from_date` | string \\| null |  | null | First day (YYYY-MM-DD, UTC); default 7 days ago. |
| `to_date` | string \\| null |  | null | Last day (inclusive); default today. |
| `scope` | string \\| null |  | null | Only this scope: code, LTER site code or name. (max length 100) |
| `kinds` | array of `insert` \\| `update` \\| `delete` \\| null |  | null | Only these: insert (new package), update (new revision), delete. |
| `offset` | integer |  | `0` | Index of the first change (paging). (>= 0) |
| `limit` | integer |  | `25` | Changes per page. (>= 1; <= 200) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `fromDate` | string |  |
| `toDate` | string |  |
| `scope` | string \\| null |  |
| `changes` | array of ChangeOut | Newest first. |
| `counts` | object of integer | Changes in the window by kind. |
| `page` | Page |  |

## edi_search_packages

**Search EDI data packages.** Search EDI/LTER data packages by free text, scope (exact, LTER site code or name such as 'Jornada'), creator last name, temporal overlap (start_year/end_year) and bounding box; sort by relevance or publication date; paginated (offset/limit). Returns the newest revision of each package with title, DOI, coverage dates, creators and keywords. Bulk generated scopes are excluded unless include_bulk=true. Next: call edi_get_package or edi_get_metadata with a packageId.

| | |
| --- | --- |
| Surface | `discovery` |
| EDI API key | optional (PASTA with a key, DataONE without) |
| Transports | http, stdio |
| Annotations | readOnly=true, destructive=false, idempotent=true, openWorld=true |
| Upstream endpoints | `GET pasta.lternet.edu/package/search/eml`<br>`GET cn.dataone.org/cn/v2/query/solr/` |

**Inputs**

| Name | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `query` | string \\| null |  | null | Free text over titles, keywords and abstracts (words, "phrases", AND/OR/NOT). Omit to browse with filters only. (max length 500) |
| `scope` | string \\| null |  | null | Only this scope. A scope (knb-lter-jrn), LTER site code (JRN) or scope name or location ('Jornada', 'Hubbard Brook'); see edi_list_scopes. (max length 100) |
| `author` | string \\| null |  | null | A creator's last name, e.g. 'Likens' (any case). (max length 100) |
| `start_year` | integer \\| null |  | null | Temporal coverage reaches this year or later. (>= 1000; <= 2200) |
| `end_year` | integer \\| null |  | null | Temporal coverage starts in this year or earlier. (>= 1000; <= 2200) |
| `bbox` | array of number \\| null |  | null | [west, south, east, north] in decimal degrees; geographic coverage must intersect it. west <= east (no antimeridian crossing). (min items 4; max items 4) |
| `sort` | `relevance` \\| `newest` \\| `oldest` |  | `"relevance"` | relevance, or publication date: newest or oldest (oldest lists undated packages first). |
| `include_bulk` | boolean |  | false | Include the generated bulk scopes (ecotrends, lter-landsat, lter-landsat-ledaps; ~36k records) when no scope is given. |
| `limit` | integer |  | `10` | Packages per page (1-50). (>= 1; <= 50) |
| `offset` | integer |  | `0` | Index of the first result (paging). (>= 0; <= 10000) |

**Result fields** (besides the common envelope)

| Field | Type | Description |
| --- | --- | --- |
| `items` | array of PackageHit |  |
| `page` | Page |  |
| `totalExact` | boolean | False on DataONE: page.total is an upper bound (superseded revisions are counted, then collapsed to one hit per package). |
