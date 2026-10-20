---
title: "Roadmap"
description: "What remains planned for edi-mcp after the sixteen tools: more edi:// resources and templates, prompts, a server.json for the MCP Registry, a Docker image and the v0.1.0 release."
type: Roadmap
tags:
  - tools
  - roadmap
  - planned
  - release
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

edi-mcp is built in seven steps, one pull request each. Steps 1–6 are done: the
scaffold and auth probe, the MCP core (registry, transports, `edi_ping`, conformance
tests), the EDI client with both backends, the four [discovery tools](discovery.md),
the [package, metadata and entity tools](packages.md), and the
[preview and download](data.md), [citation, quality and lineage](citation-and-quality.md)
and [feed](feeds.md) tools. All sixteen tools are in the [tool reference](reference.md).
What follows is **planned and not yet available**.

## Step 7 — resources, prompts and release

* More `edi://` guides and references, and resource templates for a package and its
  raw EML.
* Prompts for finding data, citing a package and planning a download.
* A `server.json` for the MCP Registry, a Docker image, and the **v0.1.0** release
  on PyPI.
