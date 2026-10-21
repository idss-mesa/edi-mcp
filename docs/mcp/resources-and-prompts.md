---
title: "Resources and prompts"
description: "The edi:// guide resources, the package and raw-EML resource templates with their cache scopes, and the three prompts edi-mcp offers."
type: Reference
tags:
  - mcp
  - resources
  - prompts
generated:
  by: "claude/opus-5.5"
  at: "2026-10-20T00:00:00Z"
sources:
  - id: mcp-resources
    resource: "https://modelcontextprotocol.io/specification/2026-07-28/server/resources"
    title: "MCP specification — Resources"
    author: "team:modelcontextprotocol"
  - id: mcp-prompts
    resource: "https://modelcontextprotocol.io/specification/2026-07-28/server/prompts"
    title: "MCP specification — Prompts"
    author: "team:modelcontextprotocol"
status: stable
---

# Resources and prompts

Besides its sixteen tools, edi-mcp offers read-only **resources**[^mcp-resources] (text
an agent or user can load into context) and **prompts**[^mcp-prompts] (task recipes a
client can offer as commands). Both work over stdio and HTTP and need no key.

## Guides and references

| URI | Content |
| --- | --- |
| `edi://guide/agent-workflow` | A five-call path from a question to cited data, input forms, keys and backends, and what to do about each error code. |
| `edi://guide/api-key` | Why EDI needs a key since 2026-07-30, how to create one, how to give it to edi-mcp (stdio and HTTP), and what works without one. |
| `edi://guide/search-syntax` | What `query` accepts and the filters of `edi_search_packages`, and how PASTA and DataONE results differ. |
| `edi://guide/package-identifiers` | `scope.identifier.revision`, `newest` / `oldest`, DOIs, entity ids, and every identifier form the tools accept. |
| `edi://guide/citing-edi-data` | Citing one revision by its DOI, the ESIP, DRYAD and BibTeX styles, and intellectual rights. |
| `edi://reference/scopes` | Every scope with its name, kind, LTER site code, location and package counts on PASTA and DataONE (a dated snapshot, JSON). |

These are the same for every caller: `resources/read` returns them with
`cacheScope: public` and a 24-hour `ttlMs`.

!!! tip "Several words are ORed"

    `edi_search_packages(query="streamflow chemistry")` finds packages with *either*
    word, on both backends. Write `streamflow AND chemistry` or
    `+streamflow +chemistry` to require both; `edi://guide/search-syntax` has the rest.

## Package templates

| Template | Returns |
| --- | --- |
| `edi://packages/{packageId}` | The `edi_get_package` summary as JSON: DOI, title, creators, license, entities and sizes. |
| `edi://packages/{packageId}/eml` | The package's raw EML document (`application/xml`). |

`packageId` is `scope.identifier.revision` (`knb-lter-hbr.14.22`) or a series
(`knb-lter-hbr.14`, meaning the newest revision); a site code works for the scope
(`jrn.210548103.32`), and a percent-encoded DOI (`doi%3A10.6073%2Fpasta%2F…`) also
resolves. The raw EML is refused with `result_too_large` above
`limits.max_resource_bytes` (1 MiB by default); `edi_get_metadata` returns a compact
projection of any EML instead.

Template reads depend on the caller. With a key they come from PASTA, which is
current and includes access-restricted packages the key may read. Without one they
come from DataONE, which can lag. They are therefore returned with
`cacheScope: private` and a one-hour `ttlMs`, so a shared cache never hands one
caller's result to another. Errors are JSON-RPC errors whose `data.code` is an
[error code](../tools/utilities.md#error-codes) such as `not_found` or `auth_required`.

## Prompts

| Prompt | Arguments | What it asks the agent to do |
| --- | --- | --- |
| `edi_find_data` | `question` (required), `place`, `years` (`YYYY` or `YYYY-YYYY`) | Check the key, search with two or three phrasings, compare the best packages' coverage and methods, check the main table's columns, and finish with a table of candidates and their citations. |
| `edi_cite_package` | `package` (required), `style` (`ESIP`, `DRYAD` or `BIBTEX`) | Get the citation and the package's intellectual rights, and present both with the DOI. |
| `edi_plan_download` | `package` (required), `entities` (comma-separated) | List the entities with sizes and checksums, preview each table, download them on stdio (or give their URLs over HTTP), and cite the package. |

Unknown or missing arguments, and invalid `style` or `years` values, are refused with
JSON-RPC `-32602` and `data.code: invalid_argument`. `prompts/list` is cached for a day
(`cacheScope: public`).

[^mcp-resources]: MCP specification — Resources. <https://modelcontextprotocol.io/specification/2026-07-28/server/resources>
[^mcp-prompts]: MCP specification — Prompts. <https://modelcontextprotocol.io/specification/2026-07-28/server/prompts>
