---
title: "Install edi-mcp"
description: "Install the edi-mcp server with uv or pip from GitHub, verify it with --version and --check, and run it from source."
type: Guide
tags:
  - getting-started
  - install
  - uv
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: uv
    resource: "https://docs.astral.sh/uv/"
    title: "uv documentation"
    author: "team:astral"
  - id: repo
    resource: "https://github.com/idss-mesa/edi-mcp"
    title: "edi-mcp source repository"
    author: "team:idss-mesa"
status: stable
stale_after: "2027-04-19T00:00:00Z"
---

# Install edi-mcp

edi-mcp is a Python 3.11+ package with one command, `edi-mcp`. The recommended
installer is [uv](https://docs.astral.sh/uv/){target=_blank}[^uv], which keeps the
server in its own environment.

!!! note "No PyPI release yet"

    edi-mcp is under construction and has not been published to PyPI; the first
    release (v0.1.0) is the last step of the build plan, although the package already
    reports that version number. Until then, install from GitHub[^repo] as shown below.

=== "uv tool (recommended)"

    ```bash
    uv tool install git+https://github.com/idss-mesa/edi-mcp
    ```

    This puts `edi-mcp` on your `PATH` (`~/.local/bin`). Upgrade with
    `uv tool upgrade edi-mcp`.

=== "uvx (no install)"

    ```bash
    uvx --from git+https://github.com/idss-mesa/edi-mcp edi-mcp --version
    ```

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
    uv sync --all-extras          # creates .venv with the package and dev tools
    uv run edi-mcp --version
    ```

    MCP clients can then run `/absolute/path/to/edi-mcp/.venv/bin/edi-mcp`.

## Verify

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

Next: [connect a client](clients.md) and [add your EDI API key](api-key.md).

[^uv]: uv documentation. <https://docs.astral.sh/uv/>
[^repo]: edi-mcp source repository. <https://github.com/idss-mesa/edi-mcp>
