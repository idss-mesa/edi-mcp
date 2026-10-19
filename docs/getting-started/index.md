# Getting started

Install edi-mcp, connect an MCP client, add your EDI API key and tune the configuration.

* [Install edi-mcp](install.md) - Install the edi-mcp server with uv or pip from GitHub, verify it with --version and --check, and run it from source.
* [Quickstart](quickstart.md) - A first session with edi-mcp: register it with Claude Code with or without an EDI API key, check it with edi_ping, search for packages and list a package's revisions.
* [EDI API key](api-key.md) - Why EDI's PASTA+ API needs a key since 2026-07-30, how to create one, how to give it to edi-mcp as EDI_API_KEY, how to check that EDI accepts it, what works without a key, and the errors a missing or refused key produces.
* [Clients](clients.md) - Register edi-mcp with Claude Code, Claude Desktop, Codex CLI, OpenCode and VS Code over stdio, or connect to a hosted server over HTTP, with the EDI API key passed through the environment.
* [Configuration](configuration.md) - Configure edi-mcp with a YAML file, EDI_MCP_ environment variables or command-line flags; precedence rules, the EDI API key, and every setting with its default.
