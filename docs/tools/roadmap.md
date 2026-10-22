---
title: "Roadmap"
description: "How edi-mcp was built in seven steps up to v0.1.0, and what is planned after it: a dry-run EML check and other opt-in additions."
type: Roadmap
tags:
  - tools
  - roadmap
  - planned
  - release
generated:
  by: "claude/opus-5.5"
  at: "2026-10-20T00:00:00Z"
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

edi-mcp was built in seven steps, one pull request each, up to **v0.1.0**:

1. the scaffold and a probe of how PASTA accepts an API key;
2. the MCP core (registry, transports, `edi_ping`, conformance tests);
3. the EDI client with its PASTA and DataONE backends;
4. the four [discovery tools](discovery.md);
5. the [package, metadata and entity tools](packages.md);
6. the [preview and download](data.md),
   [citation, quality and lineage](citation-and-quality.md) and [feed](feeds.md) tools;
7. the [resources and prompts](../mcp/resources-and-prompts.md), the MCP Registry entry
   (`server.json`), the Docker image and the release workflow.

All sixteen tools are in the [tool reference](reference.md). The PyPI package is
`edi-pasta-mcp`.

## Planned after v0.1.0

These are ideas, **not available** today:

* `edi_evaluate_package`: an opt-in dry run of EDI's EML congruence checks on a draft
  package, without publishing it. v0.1.0 is read-only.
* A published container image, in addition to the `Dockerfile`.
* A fallback for DataONE's index when it misses revisions of a package (seen on
  2026-10-20), for callers without a key.

Requests and reports: <https://github.com/idss-mesa/edi-mcp/issues>.
