# edi-mcp

[![MCP 2026-07-28](https://img.shields.io/badge/MCP-2026--07--28-blue)](https://modelcontextprotocol.io/specification/2026-07-28)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-idss--mesa.github.io%2Fedi--mcp-indigo)](https://idss-mesa.github.io/edi-mcp/)

A [Model Context Protocol](https://modelcontextprotocol.io) server (spec **2026-07-28**)
for the [Environmental Data Initiative](https://edirepository.org) (EDI) PASTA+ data
repository. It lets agents search, inspect, preview, download and cite LTER and EDI
ecological data packages.

> Documentation: <https://idss-mesa.github.io/edi-mcp/>

> **Status: under construction.** The discovery tools (`edi_ping`, search, list
> scopes/identifiers/revisions) and the package tools (`edi_get_package`,
> `edi_get_metadata`, `edi_list_entities`) work; the rest of the tools below are planned. See
> [DESIGN.md](DESIGN.md) for decisions and [RESEARCH.md](RESEARCH.md) for verified API
> facts.

## Installation

Full instructions for macOS, Linux and Windows:
<https://idss-mesa.github.io/edi-mcp/getting-started/install/>.

### Install script

`scripts/install.sh` registers the server with every supported agent it finds. It
creates the server environment with `uv sync` if `.venv/bin/edi-mcp` is missing, prefers
each agent's own CLI when one is installed (`claude mcp add`, `codex mcp add`,
`gemini mcp add`) and otherwise merges an entry into the agent's config file, keeping
everything else in the file and leaving a `.bak` copy. It needs bash and
[uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/idss-mesa/edi-mcp.git && cd edi-mcp
scripts/install.sh                               # every agent detected on this machine
scripts/install.sh --with-key                    # also store EDI_API_KEY (read from env or a hidden prompt)
scripts/install.sh --agents all --dry-run        # preview the change for every agent
scripts/install.sh --agents claude,goose         # just Claude Code and Goose
scripts/install.sh --scope project               # project-level config (claude, codex, gemini, opencode)
scripts/install.sh --env EDI_MCP_SERVER__LOG_LEVEL=debug   # any extra environment variable
scripts/install.sh --uninstall                   # remove the registration everywhere
```

| Agent | What the script does |
|---|---|
| `claude` (Claude Code) | `claude mcp add --scope user edi -- /path/to/edi-mcp/.venv/bin/edi-mcp` |
| `claude-desktop` | adds `mcpServers.edi` to `claude_desktop_config.json` |
| `codex` (OpenAI Codex CLI) | `codex mcp add edi -- …`, or an `[mcp_servers.edi]` table in `~/.codex/config.toml` |
| `gemini` (Gemini CLI) | `gemini mcp add --scope user edi …`, or `mcpServers.edi` in `~/.gemini/settings.json` |
| `goose` | adds an `edi` stdio extension to `~/.config/goose/config.yaml` |
| `opencode` | adds `mcp.servers.edi` (v2) or `mcp.edi` (v1) to `~/.config/opencode/opencode.json` |

The script writes absolute paths, because desktop apps do not inherit your shell
`PATH`. There is no option that takes the key itself; with `--with-key` the key is
stored in plain text in each agent's config (written owner-only) and never printed. On
Windows, run it from Git Bash or follow the manual steps; restart desktop apps after
installing.

### Manual

```bash
uv tool install git+https://github.com/idss-mesa/edi-mcp
claude mcp add edi -s user -e EDI_API_KEY="$EDI_API_KEY" -- edi-mcp
```

Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json` on
macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows,
`~/.config/Claude/claude_desktop_config.json` on Linux):

```json
{
  "mcpServers": {
    "edi": {
      "command": "/ABSOLUTE/PATH/TO/edi-mcp",
      "args": [],
      "env": { "EDI_API_KEY": "paste-your-key-here" }
    }
  }
}
```

Other clients (Codex CLI, Gemini CLI, Goose, OpenCode, VS Code, hosted HTTP):
<https://idss-mesa.github.io/edi-mcp/getting-started/clients/>.

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
