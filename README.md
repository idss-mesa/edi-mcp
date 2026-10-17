# edi-mcp

[![MCP 2026-07-28](https://img.shields.io/badge/MCP-2026--07--28-blue)](https://modelcontextprotocol.io/specification/2026-07-28)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A [Model Context Protocol](https://modelcontextprotocol.io) server (spec **2026-07-28**)
for the [Environmental Data Initiative](https://edirepository.org) (EDI) PASTA+ data
repository. It lets agents search, inspect, preview, download and cite LTER and EDI
ecological data packages.

> **Status: under construction.** The repository holds the scaffold and design. See
> [DESIGN.md](DESIGN.md) for decisions and [RESEARCH.md](RESEARCH.md) for verified API
> facts.

## Authentication

Since 2026-07-30 EDI requires an API key for **every** PASTA REST call, including
public reads. Create a free key at <https://auth.edirepository.org> (Profile → API
keys) and set it as `EDI_API_KEY`. Without a key, edi-mcp falls back to the anonymous
DataONE replicas of EDI content: search, metadata, entity download and citations work,
while quality reports, lineage, change feeds and read counts need a key.

## Planned tools

| Tool | Purpose |
|---|---|
| `edi_search_packages` | Search packages by keyword, scope/site, author, time and bounding box |
| `edi_list_scopes` / `edi_list_identifiers` / `edi_list_revisions` | Browse the repository hierarchy |
| `edi_get_package` | DOI, landing page, entities and sizes for one package revision |
| `edi_get_metadata` | Compact projection of the EML metadata |
| `edi_list_entities` | Data entities with names, sizes, checksums, formats and attributes |
| `edi_preview_entity` | First rows of a tabular entity |
| `edi_get_citation` | Formatted citation (ESIP, DRYAD, BibTeX) |
| `edi_get_quality_report` | PASTA congruence-check summary (key required) |
| `edi_get_lineage` | Provenance sources and descendants (key required) |
| `edi_recent_changes` | Recent inserts, updates and deletes (key required) |
| `edi_get_read_counts` | Download/read counts (key required) |
| `edi_download_entities` / `edi_download_package` | Save data locally (stdio only) |
| `edi_ping` | Server, backend and key status |

## License

MIT © 2026 The Regents of the University of New Mexico.
