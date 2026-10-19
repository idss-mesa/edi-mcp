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

Generated from the tool registry by `scripts/gen_tools_reference.py`; do not edit by hand. 5 tools are registered. Inputs are snake_case and outputs camelCase. Every result also carries `resolved`, `notes`, `nextSteps` and `source` (whose `backend` says whether PASTA or DataONE answered), and failures return `structuredContent.error` with a stable `code` (see [Utilities](utilities.md#error-codes)).

| Tool | Title | Family | EDI API key |
| --- | --- | --- | --- |
| [`edi_list_identifiers`](#edi_list_identifiers) | List package identifiers in a scope | [discovery](discovery.md) | no |
| [`edi_list_revisions`](#edi_list_revisions) | List the revisions of a package | [discovery](discovery.md) | no |
| [`edi_list_scopes`](#edi_list_scopes) | List EDI scopes | [discovery](discovery.md) | no |
| [`edi_ping`](#edi_ping) | Check edi-mcp status | [core](utilities.md) | no |
| [`edi_search_packages`](#edi_search_packages) | Search EDI data packages | [discovery](discovery.md) | no |

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
