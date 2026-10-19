---
title: "Roadmap"
description: "Tools, resources and packaging that are planned for edi-mcp but not yet released: package and entity inspection, previews, downloads, citations and the key-only PASTA services."
type: Roadmap
tags:
  - tools
  - roadmap
  - planned
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: repo
    resource: "https://github.com/idss-mesa/edi-mcp"
    title: "edi-mcp repository"
    author: "team:idss-mesa"
  - id: pasta-api
    resource: "https://pasta.lternet.edu/package/docs/api"
    title: "EDI PASTA+ Data Package Manager REST API"
    author: "team:edi"
status: stable
stale_after: "2027-01-19T00:00:00Z"
---

# Roadmap

edi-mcp is built in seven steps, one pull request each. Steps 1–4 are released on
`main`: the scaffold and auth probe, the MCP core (registry, transports, `edi_ping`,
conformance tests), the EDI client with both backends, and the four
[discovery tools](discovery.md). Everything on this page is **planned and not yet
available**; tool names and inputs may still change. The [tool reference](reference.md)
lists only what is registered today.

## Step 5 — packages, metadata and entities (in review)

| Planned tool | Purpose |
| --- | --- |
| `edi_get_package` | One revision's overview: title, publication date, creators, license, DOI, portal link, whether it is the newest revision, and its data entities with sizes. |
| `edi_get_metadata` | A compact projection of the EML metadata in selectable sections: abstract and keywords, people, geographic, temporal and taxonomic coverage, methods, license, project and funding. |
| `edi_list_entities` | Each data table or file with its columns (units, date formats, code lists, missing-value codes), its text format and optional SHA-1 checksums. |

All three work with or without a key. Raw EML stays out of tool results; the
projection is capped so large metadata documents produce compact results.

## Step 6 — previews, downloads, citations and key-only services

| Planned tool | Purpose | Key |
| --- | --- | --- |
| `edi_preview_entity` | The first rows of a tabular entity, read with a byte cap. | optional |
| `edi_download_entities` | Save data entities under the configured download directory and verify their SHA-1. stdio only. | optional |
| `edi_download_package` | Save a whole package as a zip. stdio only. | required |
| `edi_get_citation` | A formatted citation (ESIP, DRYAD or BibTeX) from `cite.edirepository.org`. | optional |
| `edi_get_quality_report` | A summary of PASTA's congruence checks for a package. | required |
| `edi_get_lineage` | Provenance: a package's sources and descendants. | required |
| `edi_recent_changes` | Recent inserts, updates and deletes, by date or scope. | required |
| `edi_get_read_counts` | Download and read counts for a package. | required |

"Required" tools have no DataONE counterpart and will return `auth_required` without
a key (see [Backends](backends.md)). Downloads will be the only tools that write,
will never overwrite, and will be offered only over stdio.

## Step 7 — resources, prompts and release

* More `edi://` guides and references, and resource templates for a package and its
  raw EML.
* Prompts for finding data, citing a package and planning a download.
* A `server.json` for the MCP Registry, a Docker image, and the **v0.1.0** release
  on PyPI.
