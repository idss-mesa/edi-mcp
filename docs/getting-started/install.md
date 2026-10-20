---
title: "Install edi-mcp"
description: "Install edi-mcp on macOS, Linux or Windows: prerequisites, the install script that registers the server with Claude Code, Claude Desktop, Codex, Gemini CLI, Goose and OpenCode, manual registration, verification, troubleshooting, upgrades and removal."
type: Guide
tags:
  - getting-started
  - install
  - uv
  - install-script
  - windows
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: uv
    resource: "https://docs.astral.sh/uv/"
    title: "uv documentation"
    author: "team:astral"
  - id: uv-install
    resource: "https://docs.astral.sh/uv/getting-started/installation/"
    title: "Installing uv"
    author: "team:astral"
  - id: repo
    resource: "https://github.com/idss-mesa/edi-mcp"
    title: "edi-mcp source repository"
    author: "team:idss-mesa"
status: stable
stale_after: "2027-04-19T00:00:00Z"
---

# Install edi-mcp

edi-mcp is a Python 3.11+ package with one command, `edi-mcp`, that MCP clients start
over stdio. These instructions cover macOS, Linux and Windows.

!!! note "No PyPI release yet"

    edi-mcp is under construction and has not been published to PyPI; the first
    release (v0.1.0) is the last step of the build plan, although the package already
    reports that version number. Until then, install from GitHub[^repo] as shown below.

## Prerequisites

- [uv](https://docs.astral.sh/uv/){target=_blank}[^uv], which installs Python 3.11+
  for edi-mcp if your system lacks it, and keeps the server in its own environment.
- git, for the install script and installs from source.
- Optional: an [EDI API key](api-key.md). Without one, edi-mcp answers from the
  anonymous DataONE replicas of EDI content.

Install uv[^uv-install]:

=== "macOS"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # or: brew install uv
    ```

=== "Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

=== "Windows (PowerShell)"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    # or: winget install --id=astral-sh.uv -e
    ```

Open a new terminal afterwards so `uv` is on your `PATH`.

## Option 1: From source with the install script (recommended)

```bash
git clone https://github.com/idss-mesa/edi-mcp.git
cd edi-mcp
scripts/install.sh
```

`scripts/install.sh` creates the server environment (`uv sync`) if `.venv/bin/edi-mcp`
is missing, then registers that executable with every supported agent it finds on
your machine: Claude Code, Claude Desktop, OpenAI Codex CLI, Gemini CLI, Goose and
OpenCode. It prefers each agent's own CLI when one is installed (`claude mcp add`,
`codex mcp add`, `gemini mcp add`) and otherwise merges an entry into the agent's
config file, keeping everything else in the file and leaving a `.bak` copy.

```bash
scripts/install.sh --with-key                    # also store your EDI API key (see below)
scripts/install.sh --agents all --dry-run        # preview the change for every agent
scripts/install.sh --agents claude,goose         # just Claude Code and Goose
scripts/install.sh --scope project               # project-level config (claude, codex, gemini, opencode)
scripts/install.sh --env EDI_MCP_SERVER__LOG_LEVEL=debug   # any extra environment variable
scripts/install.sh --command "$(command -v edi-mcp)"       # register a uv-tool install instead
scripts/install.sh --uninstall                   # remove the registration everywhere
```

| Agent | What the script does |
| --- | --- |
| `claude` (Claude Code) | `claude mcp add --scope user edi -- /path/to/edi-mcp/.venv/bin/edi-mcp` |
| `claude-desktop` | adds `mcpServers.edi` to `claude_desktop_config.json` |
| `codex` (OpenAI Codex CLI) | `codex mcp add edi -- …`, or an `[mcp_servers.edi]` table in `~/.codex/config.toml` |
| `gemini` (Gemini CLI) | `gemini mcp add --scope user edi …`, or `mcpServers.edi` in `~/.gemini/settings.json` |
| `goose` | adds an `edi` stdio extension to `~/.config/goose/config.yaml` |
| `opencode` | adds `mcp.servers.edi` (v2) or `mcp.edi` (v1) to `~/.config/opencode/opencode.json` |

The script writes the absolute path of the executable, because desktop apps do not
inherit your shell `PATH`. It needs bash; macOS's built-in bash 3.2 is enough. Restart
desktop apps (Claude Desktop, Goose Desktop) after installing.

### The EDI API key and the script

There is deliberately no option that takes the key itself, since command lines end
up in shell history and process lists. `--with-key` reads `EDI_API_KEY` from your
environment, or asks for it with hidden input, and writes it into each agent's server
`env`:

```bash
read -rs EDI_API_KEY && export EDI_API_KEY     # paste the key, press Enter
scripts/install.sh --with-key
```

- The key is then stored **in plain text** in each agent's config file. The script
  restricts the files it writes, and their `.bak` copies, to your user (mode `600`),
  and masks the key as `***` in everything it prints, including the output of the
  agent CLIs it calls.
- For agents registered through their own CLI (Claude Code, Codex, Gemini CLI), the
  key is passed to that CLI's `mcp add` command and is briefly visible in the process
  list. Add `--prefer-files` to have Codex and Gemini CLI configured by file instead.
- Without `--with-key` no key is stored, and the server uses the anonymous DataONE
  backend unless the agent passes `EDI_API_KEY` to it some other way.

### Windows

On Windows, register by hand (Option 2) or run the script from **Git Bash**, which
converts paths to Windows form and writes Claude Desktop's config under `%APPDATA%`.
Git Bash support has not been tested as widely as macOS and Linux; check the result
with `--dry-run` first. Do not run the script inside WSL to configure Windows apps:
it would write WSL's own config files, which Claude Desktop for Windows never reads.

## Option 2: Install the package and register it by hand

Install the `edi-mcp` command:

=== "uv tool (recommended)"

    ```bash
    uv tool install git+https://github.com/idss-mesa/edi-mcp
    ```

    This puts `edi-mcp` in uv's tool directory (`~/.local/bin` on macOS and Linux,
    `%USERPROFILE%\.local\bin` on Windows). Upgrade with `uv tool upgrade edi-mcp`.

=== "uvx (no install)"

    ```bash
    uvx --from git+https://github.com/idss-mesa/edi-mcp edi-mcp --version
    ```

    Clients can use `uvx` as the command with
    `["--from", "git+https://github.com/idss-mesa/edi-mcp", "edi-mcp"]` as its
    arguments; the first start is slower while uv builds the environment.

=== "pipx / pip"

    ```bash
    pipx install git+https://github.com/idss-mesa/edi-mcp
    # or, inside a virtual environment:
    pip install "git+https://github.com/idss-mesa/edi-mcp"
    ```

=== "From source"

    ```bash
    git clone https://github.com/idss-mesa/edi-mcp
    cd edi-mcp
    uv sync                      # creates .venv with the package
    uv run edi-mcp --version
    ```

Then find the executable's absolute path, which is what desktop apps need:

=== "macOS / Linux"

    ```bash
    command -v edi-mcp           # e.g. /Users/you/.local/bin/edi-mcp
    # from source: /path/to/edi-mcp/.venv/bin/edi-mcp
    ```

=== "Windows (PowerShell)"

    ```powershell
    (Get-Command edi-mcp).Source  # e.g. C:\Users\you\.local\bin\edi-mcp.exe
    # from source: C:\path\to\edi-mcp\.venv\Scripts\edi-mcp.exe
    ```

and register it with your client. The shortest form, for Claude Code:

```bash
claude mcp add edi -s user -e EDI_API_KEY="$EDI_API_KEY" -- edi-mcp
```

Claude Desktop, and other JSON-configured clients:

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

Use absolute paths (not `~/` or `./`). On Windows escape backslashes:
`"C:\\Users\\You\\.local\\bin\\edi-mcp.exe"`. Leave out `env` to run without a key.
[Clients](clients.md) has the entries for Claude Desktop, Codex CLI, Gemini CLI,
Goose, OpenCode, VS Code and hosted servers.

## Option 3: Docker

A container image (`python:3.13-slim`, non-root, HTTP on port 8080 with a `/healthz`
check) is planned for the v0.1.0 release; see the [Roadmap](../tools/roadmap.md).
There is no Dockerfile yet.

## Verify the installation

```bash
edi-mcp --version     # edi-mcp 0.1.0
edi-mcp --check       # {"ok": true, "version": "0.1.0", "protocolVersion": "2026-07-28", "transport": "stdio", "keyConfigured": false, "backend": "dataone"}
```

`--check` loads your configuration, calls `edi_ping` in-process and prints a one-line
JSON report: the version, protocol, transport, whether an EDI API key is configured
and which backend that selects (`pasta` with a key, `dataone` without). It makes no
network request, so it does not prove that EDI accepts your key. For that, ask your
agent to call `edi_ping` with `check_api=true` once the server is connected; see
[EDI API key](api-key.md#check-the-key). `--print-config` shows the effective settings
with the key replaced by `***`.

In Claude Code, `claude mcp list` runs a health check and shows `edi` as connected. To
talk to the server directly over stdio:

```bash
# 2026-07-28 client: every request carries the protocol envelope in _meta
echo '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{},"io.modelcontextprotocol/clientInfo":{"name":"manual","version":"0"}}}}' \
  | edi-mcp

# 2025-era client: classic initialize handshake, then tools/list
printf '%s\n%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | edi-mcp
```

Both print JSON-RPC responses on stdout (logs go to stderr) and exit once stdin
closes. `server/discover` reports the server's capabilities and instructions; a
`tools/list` request with the same `_meta` envelope lists every tool (see the
[Tool reference](../tools/reference.md)).

## Configuration

Nothing is required. The settings most people touch:

```bash
EDI_API_KEY=                      # optional; PASTA with it, DataONE without
EDI_MCP_SERVER__LOG_LEVEL=info    # debug | info | warning | error | critical (stderr)
EDI_MCP_DOWNLOADS__DIRECTORY=     # where the download tools write (default ~/edi-downloads)
```

edi-mcp does not read `.env` files on its own. See [Configuration](configuration.md)
for every setting, the YAML file and the precedence rules.

## Troubleshooting

**`edi-mcp: command not found` from a desktop app.** Desktop apps do not read your
shell profile. Use the executable's absolute path as the `command`; the install script
does this for you.

**Server shows as disconnected.** Run the configured command yourself with
`--check`. If it fails, re-create the environment (`uv sync` in a clone, or
`uv tool install --reinstall git+https://github.com/idss-mesa/edi-mcp`). Claude Desktop
logs live in `~/Library/Logs/Claude/` (macOS) or `%APPDATA%\Claude\logs\` (Windows);
in Claude Code, `claude mcp get edi` shows the connection status.

**`backend` is `dataone` although you have a key.** The key did not reach the server
process: desktop apps do not see variables exported in your shell. Put it in the
client's `env` block, or re-run the install script with `--with-key`.

**`upstream_forbidden` errors.** EDI refused the key; without a `reason` it is
mistyped, expired or deleted. With `reason: access_restricted` the key works but the
package is restricted. See [EDI API key](api-key.md#errors).

**Port already in use.** MCP over stdio uses no network port; a port error comes from
an HTTP deployment (`--transport http`, port 8080 by default) or something else on your
machine.

**Windows paths.** In JSON, write backslashes doubled (`C:\\Users\\…`) or use forward
slashes. Point at `edi-mcp.exe`, not the extension-less name.

## Upgrading

```bash
# install script / from source
git pull origin main && uv sync
# uv tool
uv tool upgrade edi-mcp
```

Registrations made by the install script keep pointing at `.venv/bin/edi-mcp`, so
`git pull && uv sync` is enough; restart desktop apps afterwards.

## Uninstallation

`--uninstall` leaves each edited file's `.bak` copy behind; if you used `--with-key`,
those backups (owner-only, like the files) still contain the key, so delete them too.

```bash
scripts/install.sh --uninstall   # remove the server from every agent config
cd .. && rm -rf edi-mcp          # if installed from source
uv tool uninstall edi-mcp        # if installed with uv tool
```

## Next steps

- [Quickstart](quickstart.md): a first session.
- [EDI API key](api-key.md): create a key and give it to edi-mcp.
- [Clients](clients.md): per-client configuration.
- [Configuration](configuration.md): every setting.

[^uv]: uv documentation. <https://docs.astral.sh/uv/>
[^uv-install]: Installing uv. <https://docs.astral.sh/uv/getting-started/installation/>
[^repo]: edi-mcp source repository. <https://github.com/idss-mesa/edi-mcp>
