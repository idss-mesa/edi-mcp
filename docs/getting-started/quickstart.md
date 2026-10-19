---
title: "Quickstart"
description: "A first session with edi-mcp: register it with Claude Code with or without an EDI API key, check it with edi_ping, search for packages and list a package's revisions."
type: Tutorial
tags:
  - getting-started
  - quickstart
  - tutorial
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: claude-code-mcp
    resource: "https://docs.claude.com/en/docs/claude-code/mcp"
    title: "Claude Code — MCP"
    author: "team:anthropic"
  - id: pasta-api
    resource: "https://pasta.lternet.edu/package/docs/api"
    title: "EDI PASTA+ Data Package Manager REST API"
    author: "team:edi"
status: stable
stale_after: "2027-04-19T00:00:00Z"
---

# Quickstart

This walks through a first session in Claude Code[^claude-code-mcp]; other clients
work the same way once connected ([Clients](clients.md)). It uses the tools available
today: `edi_ping`, the discovery tools (`edi_search_packages`, `edi_list_scopes`,
`edi_list_identifiers`, `edi_list_revisions`) and the package tools (`edi_get_package`,
`edi_get_metadata`, `edi_list_entities`). Preview, download and citation tools are still
being built; see the [Roadmap](../tools/roadmap.md).

## 1. Register the server

edi-mcp works with or without an EDI API key. With a key it reads EDI's own PASTA+ API;
without one it falls back to the anonymous DataONE replicas of EDI content (see
[Backends](../tools/backends.md)).

=== "With an EDI API key"

    Create a key at [auth.edirepository.org](https://auth.edirepository.org/auth/ui/key){target=_blank}
    ([step by step](api-key.md#create-a-key)) and export it as `EDI_API_KEY` without
    echoing it to the terminal:

    ```bash
    read -rs EDI_API_KEY && export EDI_API_KEY     # paste the key, press Enter
    claude mcp add edi -s user -e EDI_API_KEY="$EDI_API_KEY" -- edi-mcp --transport stdio
    ```

=== "Without a key"

    ```bash
    claude mcp add edi -s user -- edi-mcp --transport stdio
    ```

    Search and the listing tools answer from DataONE, which can lag new EDI uploads.
    `edi_list_scopes` then serves a dated snapshot instead of the live list.

## 2. Check it

Ask the agent to "call edi_ping with check_api=true". The result shows the version,
protocol `2026-07-28`, `keyConfigured`, the `backend` serving you (`pasta` or
`dataone`) and, under `api`, whether one small request to that backend succeeded. With
a key, `api.credential` is `token` when edi-mcp exchanged the key for a short-lived
`edi-token`. The key itself never appears in any result.

## 3. Find and inspect a package

The agent normally chains these on its own; the arguments below are what it sends.
Results are abbreviated, and the package ids are examples: what a search returns
depends on the backend and on what EDI holds at the time.

1. **Search**

    ```json
    {"tool": "edi_search_packages", "arguments": {"query": "net primary production", "scope": "Jornada"}}
    ```

    → `resolved: [{"field": "scope", "input": "Jornada", "code": "knb-lter-jrn", ...}]`
    and `items`, each with `packageId` (such as `knb-lter-jrn.210548103.33`), `title`,
    `pubDate`, `doi`, `authors`, `keywords` and `portalUrl`, plus `page` for paging and
    `source.backend`. Scopes accept exact names (`knb-lter-jrn`), LTER site codes (`JRN`)
    and names (`Jornada`); see [Package identifiers](../tools/identifiers.md).

2. **List the revisions of one package**

    ```json
    {"tool": "edi_list_revisions", "arguments": {"package": "jrn.210548103"}}
    ```

    → `series: "knb-lter-jrn.210548103"`, the `revisions` in ascending order, `newest`,
    `oldest` and `newestPackageId`. Without a key, DataONE answers and may not yet hold
    the newest revision PASTA has.

3. **Browse a scope**

    ```json
    {"tool": "edi_list_identifiers", "arguments": {"scope": "HBR"}}
    ```

    → the package identifiers in `knb-lter-hbr`, ascending and paged.

4. **Read one package**

    ```json
    {"tool": "edi_get_package", "arguments": {"package": "knb-lter-hbr.14.22"}}
    ```

    → `title`, `doi`, `license`, `isNewest`, and `entities` with sizes and
    `totalBytes`. Then `edi_get_metadata` (with `include` such as
    `["overview", "coverage"]`) gives the abstract, keywords and coverage, and
    `edi_list_entities` gives each table's columns, units and missing-value codes,
    with a PASTA `dataUrl` and, where DataONE replicates the scope, a keyless
    `anonymousUrl`. See [Packages, metadata and entities](../tools/packages.md).

Every result also carries `notes` (caveats such as DataONE lag) and `nextSteps`
(concrete follow-up calls). The [Tool reference](../tools/reference.md) lists every
input and result field.

[^claude-code-mcp]: Claude Code — MCP. <https://docs.claude.com/en/docs/claude-code/mcp>
[^pasta-api]: EDI PASTA+ Data Package Manager REST API. <https://pasta.lternet.edu/package/docs/api>
