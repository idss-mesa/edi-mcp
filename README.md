# edi-mcp

[![MCP 2026-07-28](https://img.shields.io/badge/MCP-2026--07--28-blue)](https://modelcontextprotocol.io/specification/2026-07-28)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-idss--mesa.github.io%2Fedi--mcp-indigo)](https://idss-mesa.github.io/edi-mcp/)
[![PyPI](https://img.shields.io/pypi/v/edi-pasta-mcp)](https://pypi.org/project/edi-pasta-mcp/)

<!-- mcp-name: io.github.idss-mesa/edi-mcp -->

A [Model Context Protocol](https://modelcontextprotocol.io) server (spec **2026-07-28**)
for the [Environmental Data Initiative](https://edirepository.org) (EDI) PASTA+ data
repository. It lets agents search, inspect, preview, download and cite LTER and EDI
ecological data packages.

> Documentation: <https://idss-mesa.github.io/edi-mcp/>

> **Status: v0.1.0.** 16 read-only tools, 6 guide resources, 2 package templates and 3
> prompts. The PyPI distribution is **`edi-pasta-mcp`** (the name `edi-mcp` belongs to an
> unrelated project); it installs the command `edi-mcp` (also available as `edi-pasta-mcp`). See [DESIGN.md](DESIGN.md)
> for decisions and [RESEARCH.md](RESEARCH.md) for verified API facts.

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
uv tool install edi-pasta-mcp         # or run it without installing: uvx edi-pasta-mcp
claude mcp add edi -s user -e EDI_API_KEY="$EDI_API_KEY" -- edi-mcp
```

`pip install edi-pasta-mcp` and `pipx install edi-pasta-mcp` work too; the
development version installs from `git+https://github.com/idss-mesa/edi-mcp`. Do not
`pip install edi-mcp`: that is a different, unrelated package.

### Docker (HTTP)

```bash
docker build -t edi-mcp .
docker run --rm -p 127.0.0.1:8080:8080 edi-mcp      # MCP at http://127.0.0.1:8080/mcp
```

The image serves stateless Streamable HTTP as a non-root user, with `/healthz` and
`/readyz`. Callers send their own key in `X-EDI-Key`, which edi-mcp accepts only behind
TLS (`EDI_MCP_SERVER__PUBLIC_BASE_URL=https://…`); see
<https://idss-mesa.github.io/edi-mcp/deploy/hosted-http/> and `docker-compose.yml`.

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
DataONE replicas of EDI content: search, metadata, entity previews and downloads, quality
reports and citations work, while lineage, the change feed, read counts and whole-package
zips need a key.

## Tools

| Tool | Purpose |
|---|---|
| `edi_search_packages` | Search packages by keyword, scope/site, author, time and bounding box |
| `edi_list_scopes` / `edi_list_identifiers` / `edi_list_revisions` | Browse the repository hierarchy |
| `edi_get_package` | DOI, landing page, entities and sizes for one package revision |
| `edi_get_metadata` | Compact projection of the EML metadata |
| `edi_list_entities` | Data entities with names, sizes, checksums, formats and attributes |
| `edi_preview_entity` | First rows of a delimited entity, streamed and parsed with its EML layout |
| `edi_get_citation` | Formatted citation (ESIP, DRYAD, BibTeX) |
| `edi_get_quality_report` | PASTA congruence-check summary: counts and non-valid checks |
| `edi_get_lineage` | Provenance sources and descendants (key required) |
| `edi_recent_changes` | Recent inserts, updates and deletes (key required) |
| `edi_get_read_counts` | Read counts by resource type and revision (key required) |
| `edi_download_entities` / `edi_download_package` | Save entities (SHA-1 verified, never overwriting) or the zip (key) locally; stdio only |
| `edi_ping` | Server, backend and key status |

## Resources and prompts

| Resource | Content |
|---|---|
| `edi://guide/agent-workflow` | Five-call recipe from a question to cited data, input forms, error remedies |
| `edi://guide/api-key` | Why EDI needs a key, how to create and pass one, what works without |
| `edi://guide/search-syntax` | Query text (words are ORed), filters, PASTA vs DataONE differences |
| `edi://guide/package-identifiers` | scope.identifier.revision, DOIs, entity ids, accepted forms |
| `edi://guide/citing-edi-data` | Citing one revision by its DOI, styles, rights |
| `edi://reference/scopes` | Every scope with name, kind, site code and package counts |
| `edi://packages/{packageId}` | Template: the `edi_get_package` summary |
| `edi://packages/{packageId}/eml` | Template: the raw EML document (up to 1 MiB) |

Prompts: `edi_find_data` (question → candidate packages), `edi_cite_package` (citation
plus rights) and `edi_plan_download` (size, preview, download, cite).

## License

MIT © 2026 The Regents of the University of New Mexico.
