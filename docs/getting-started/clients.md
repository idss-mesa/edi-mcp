---
title: "Clients"
description: "Register edi-mcp with Claude Code, Claude Desktop, Codex CLI, Gemini CLI, Goose, OpenCode and VS Code over stdio, by hand or with the install script, or connect to a hosted server over HTTP, with the EDI API key passed through the environment."
type: Guide
tags:
  - getting-started
  - clients
  - claude-code
  - codex
  - gemini
  - goose
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: claude-code-mcp
    resource: "https://docs.claude.com/en/docs/claude-code/mcp"
    title: "Claude Code — MCP"
    author: "team:anthropic"
  - id: codex-mcp
    resource: "https://developers.openai.com/codex/cli/"
    title: "OpenAI Codex CLI"
    author: "team:openai"
  - id: gemini-mcp
    resource: "https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md"
    title: "Gemini CLI — MCP servers"
    author: "team:google"
  - id: goose-ext
    resource: "https://block.github.io/goose/docs/getting-started/using-extensions"
    title: "Goose — Using extensions"
    author: "team:block"
  - id: opencode-mcp
    resource: "https://opencode.ai/docs/mcp-servers/"
    title: "OpenCode — MCP servers"
    author: "team:opencode"
  - id: vscode-mcp
    resource: "https://code.visualstudio.com/docs/copilot/chat/mcp-servers"
    title: "VS Code — Use MCP servers"
    author: "team:microsoft"
status: stable
stale_after: "2027-04-19T00:00:00Z"
---

# Clients

Local clients start edi-mcp themselves over **stdio**; hosted deployments are reached
over **Streamable HTTP**. The [install script](install.md#option-1-from-source-with-the-install-script-recommended)
(`scripts/install.sh`) writes the stdio entries below for Claude Code, Claude Desktop,
Codex CLI, Gemini CLI, Goose and OpenCode in one step; this page shows them for manual
setup. The examples use `edi-mcp` on your `PATH` (see
[Install](install.md)); replace it with an absolute path such as
`/home/me/edi-mcp/.venv/bin/edi-mcp` when the client does not share your shell's
`PATH`. JSON-configured clients do not expand `~` or `$HOME`, so use absolute paths
there.

The key is optional; [EDI API key](api-key.md) shows how to create one. Every example
passes it as `EDI_API_KEY`, the name EDI's own guides use. Put it in the client's
environment settings, never in a shared or committed file. Leave it out and edi-mcp
uses the anonymous DataONE backend.

## Claude Code

```bash
claude mcp add edi -s user -e EDI_API_KEY="$EDI_API_KEY" -- edi-mcp --transport stdio
claude mcp list
```

`-s user` makes the server available in every project[^claude-code-mcp]; drop the `-e`
option to run without a key.

## Claude Desktop

Edit `claude_desktop_config.json` and restart the app:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "edi": {
      "command": "/absolute/path/to/edi-mcp",
      "args": ["--transport", "stdio"],
      "env": { "EDI_API_KEY": "paste-your-key-here" }
    }
  }
}
```

## Codex CLI

```bash
codex mcp add edi --env EDI_API_KEY="$EDI_API_KEY" -- edi-mcp --transport stdio
codex mcp list
```

This writes the server into `~/.codex/config.toml`[^codex-mcp]; restart running
sessions.

Without the CLI, add the table to `~/.codex/config.toml` yourself:

```toml
[mcp_servers.edi]
command = "/absolute/path/to/edi-mcp"
args = []

[mcp_servers.edi.env]
EDI_API_KEY = "paste-your-key-here"
```

## Gemini CLI

```bash
gemini mcp add --scope user -e EDI_API_KEY="$EDI_API_KEY" edi edi-mcp
gemini mcp list
```

or add the entry to `~/.gemini/settings.json`[^gemini-mcp] (`.gemini/settings.json` in a
project):

```json
{
  "mcpServers": {
    "edi": {
      "command": "/absolute/path/to/edi-mcp",
      "args": [],
      "env": { "EDI_API_KEY": "paste-your-key-here" }
    }
  }
}
```

## Goose

Add an extension to `~/.config/goose/config.yaml` (Windows:
`%APPDATA%\Block\goose\config\config.yaml`)[^goose-ext], then restart Goose Desktop or
start a new CLI session. `goose configure` → *Add Extension* → *Command-line Extension*
does the same interactively.

```yaml
extensions:
  edi:
    enabled: true
    type: stdio
    name: edi
    cmd: /absolute/path/to/edi-mcp
    args: []
    envs:
      EDI_API_KEY: paste-your-key-here
    timeout: 300
```

## OpenCode

Add to `~/.config/opencode/opencode.json`[^opencode-mcp]. This is the layout
OpenCode's documentation shows. The install script, following gbif-mcp's, writes
`"mcp": {"servers": {…}}` instead unless `opencode --version` reports 1.x; if your
OpenCode does not pick the server up, move the entry to the layout its documentation
gives.

```json
{
  "mcp": {
    "edi": {
      "type": "local",
      "command": ["/absolute/path/to/edi-mcp", "--transport", "stdio"],
      "enabled": true,
      "environment": { "EDI_API_KEY": "paste-your-key-here" }
    }
  }
}
```

## VS Code

Add to `.vscode/mcp.json` in a workspace, or to your user configuration[^vscode-mcp].
An `inputs` prompt keeps the key out of the file:

```json
{
  "inputs": [
    { "type": "promptString", "id": "edi-api-key", "description": "EDI API key", "password": true }
  ],
  "servers": {
    "edi": {
      "type": "stdio",
      "command": "/absolute/path/to/edi-mcp",
      "args": ["--transport", "stdio"],
      "env": { "EDI_API_KEY": "${input:edi-api-key}" }
    }
  }
}
```

## Any other stdio client

Run `edi-mcp --transport stdio` (bare `edi-mcp` does the same) with the key in the
environment. The server speaks MCP 2026-07-28 and still accepts clients on earlier
protocol revisions over stdio.

## A hosted server (HTTP)

```bash
claude mcp add --transport http edi https://edi-mcp.example.org/mcp \
  --header "X-EDI-Key: $EDI_API_KEY"
```

Each user sends their own key in `X-EDI-Key`; the server honours it only when its
`public_base_url` is `https://` (see [Transports](../mcp/transports.md)). Over HTTP the
planned download tools are not offered.

[^claude-code-mcp]: Claude Code — MCP. <https://docs.claude.com/en/docs/claude-code/mcp>
[^codex-mcp]: OpenAI Codex CLI. <https://developers.openai.com/codex/cli/>
[^gemini-mcp]: Gemini CLI — MCP servers. <https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md>
[^goose-ext]: Goose — Using extensions. <https://block.github.io/goose/docs/getting-started/using-extensions>
[^opencode-mcp]: OpenCode — MCP servers. <https://opencode.ai/docs/mcp-servers/>
[^vscode-mcp]: VS Code — Use MCP servers. <https://code.visualstudio.com/docs/copilot/chat/mcp-servers>
