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

edi-mcp is built in seven steps, one pull request each. Steps 1–5 are released on
`main`: the scaffold and auth probe, the MCP core (registry, transports, `edi_ping`,
conformance tests), the EDI client with both backends, the four
[discovery tools](discovery.md), and the [package, metadata and entity tools](packages.md). Everything on this page is **planned and not yet
available**; tool names and inputs may still change. The [tool reference](reference.md)
lists only what is registered today.

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
