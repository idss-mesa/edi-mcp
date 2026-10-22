---
okf_version: "0.2"
title: edi-mcp
description: "edi-mcp is a Model Context Protocol (MCP 2026-07-28) server that gives AI agents compact, size-bounded access to the Environmental Data Initiative (EDI) PASTA+ repository of LTER and EDI ecological data packages."
---

# edi-mcp

**edi-mcp** is a [Model Context Protocol](https://modelcontextprotocol.io/){target=_blank}
server for the [Environmental Data Initiative](https://edirepository.org/){target=_blank}
(EDI) data repository, PASTA+. EDI holds many thousands of ecological data
packages from the Long Term Ecological Research (LTER) network and many other
projects, each described by EML metadata and published under a DOI. edi-mcp
lets AI agents and coding assistants search those packages and walk the
repository's scopes, identifiers and revisions, read a package's EML
metadata, preview and download its data, and cite it, through compact,
size-bounded tool results.

The server implements the **MCP 2026-07-28** specification (stateless core)
on the Python `mcp` 2.x SDK. It speaks `stdio` for local clients such as
Claude Code and Claude Desktop, and stateless Streamable HTTP at `/mcp` when
hosted. It is developed by [idss-mesa](https://github.com/idss-mesa){target=_blank}
at the University of New Mexico and released under the MIT license.

!!! note "Version 0.1.0"

    Sixteen read-only tools (see the [Tool reference](tools/reference.md)), six
    guide resources, two package templates and three prompts (see
    [Resources and prompts](mcp/resources-and-prompts.md)). The PyPI package is
    **`edi-pasta-mcp`**: `edi-mcp` on PyPI is an unrelated project.

## Install in one minute

```bash
uv tool install edi-pasta-mcp
claude mcp add edi -s user -e EDI_API_KEY="$EDI_API_KEY" -- edi-mcp
```

Then ask your agent to call `edi_ping`; the reply says which backend
answers your calls and whether a key is configured.

!!! note "With or without an EDI API key"

    Since 2026-07-30 EDI's PASTA API requires an API key for every request,
    including reads of public data. With a key in `EDI_API_KEY`, edi-mcp
    talks to PASTA. Without one, it falls back to the anonymous
    [DataONE](https://www.dataone.org/){target=_blank} replicas of EDI
    content, so discovery still works. A key that EDI rejects is reported as
    an error, never silently downgraded. See [EDI API key](getting-started/api-key.md)
    and [Backends](tools/backends.md).

## Documentation

This site is an [Open Knowledge Format (OKF) v0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md){target=_blank}
knowledge bundle: every page carries YAML frontmatter with `type`,
provenance and lifecycle fields, and the whole corpus is available to agents
at [`llms.txt`](llms.txt) and [`llms-full.txt`](llms-full.txt).

* [Getting started](getting-started/index.md) - Install edi-mcp, connect an MCP client, add your EDI API key and tune the configuration.
* [Tools](tools/index.md) - The sixteen tools with the generated reference, package inspection, previews and downloads, citations and quality reports, feeds, identifiers, the PASTA and DataONE backends, error codes and the roadmap.
* [MCP protocol](mcp/index.md) - How edi-mcp implements the MCP 2026-07-28 stateless core and its stdio and Streamable HTTP transports.
* [Deploy](deploy/index.md) - Run edi-mcp as a hosted, stateless HTTP service behind TLS, and the security model operators rely on.
* [Develop](develop/index.md) - Architecture, adding a tool, the hermetic test suite with recorded fixtures, and how to contribute.
* [About](about/index.md) - How agents should consume this site, how to cite EDI data, licenses, and the change log.

## Where to get help

* Bugs and feature requests: [GitHub issues](https://github.com/idss-mesa/edi-mcp/issues){target=_blank}.
* Questions about the data themselves: the [EDI Data Portal](https://portal.edirepository.org/){target=_blank}
  and the [PASTA+ API documentation](https://pasta.lternet.edu/package/docs/api){target=_blank}.
