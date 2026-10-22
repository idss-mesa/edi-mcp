# MCP protocol

How edi-mcp implements the Model Context Protocol 2026-07-28 and its two transports.

* [MCP 2026-07-28 conformance](spec-2026-07-28.md) - Which parts of the MCP 2026-07-28 stateless core edi-mcp implements — discovery, cache hints, result types, schemas, _meta, MRTR — and which deprecated features it deliberately leaves out.
* [Transports](transports.md) - The stdio and stateless Streamable HTTP transports: routes, health checks, header routing, DNS-rebinding protection and per-request EDI API keys.
* [Resources and prompts](resources-and-prompts.md) - The edi:// guide resources, the package and raw-EML resource templates with their cache scopes, and the three prompts edi-mcp offers.
