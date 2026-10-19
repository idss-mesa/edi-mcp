"""scripts/install.sh: agent config edits in a sandboxed HOME, and the key never printed.

The script runs with an empty HOME, a PATH holding only basic tools (no agent CLIs, so
every agent goes through its config file) and ``--command`` / ``--no-sync``, so it needs
no network and never touches the developer's real agent configs.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "install.sh"
FAKE_KEY = "test-not-a-real-key-0123456789"
SERVER = "/opt/edi-mcp/bin/edi-mcp"
TOOLS = ("bash", "uname", "dirname", "sed", "grep", "head", "tr", "cat")

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None, reason="needs a POSIX bash"
)


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool)
        assert found, tool
        (bin_dir / tool).symlink_to(found)
    return tmp_path


def run(
    sandbox: Path, *args: str, key: str | None = None, extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        "HOME": str(sandbox / "home"),
        "PATH": str(sandbox / "bin"),
        "EDI_INSTALL_PYTHON": sys.executable,
        **(extra or {}),
    }
    if key is not None:
        env["EDI_API_KEY"] = key
    return subprocess.run(
        [shutil.which("bash") or "bash", str(SCRIPT), "--command", SERVER, "--no-sync", *args],
        env=env,
        cwd=sandbox,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def paths(sandbox: Path) -> dict[str, Path]:
    home = sandbox / "home"
    desktop = (
        home / "Library/Application Support/Claude/claude_desktop_config.json"
        if sys.platform == "darwin"
        else home / ".config/Claude/claude_desktop_config.json"
    )
    return {
        "claude-desktop": desktop,
        "codex": home / ".codex/config.toml",
        "gemini": home / ".gemini/settings.json",
        "goose": home / ".config/goose/config.yaml",
        "opencode": home / ".config/opencode/opencode.json",
    }


def seed(sandbox: Path) -> dict[str, Path]:
    """Pre-existing configs, each with an unrelated entry that must survive."""
    p = paths(sandbox)
    for path in p.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    p["claude-desktop"].write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    p["gemini"].write_text(json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "x"}}}))
    p["codex"].write_text('model = "o4"\n\n[mcp_servers.other]\ncommand = "x"\n')
    p["goose"].write_text(
        "GOOSE_PROVIDER: openai\nextensions:\n  developer:\n    enabled: true\n    type: builtin\n"
    )
    p["opencode"].write_text(json.dumps({"mcp": {"servers": {"other": {"type": "local"}}}}))
    return p


def entries(p: dict[str, Path]) -> dict[str, dict[str, object]]:
    goose = yaml.safe_load(p["goose"].read_text())
    return {
        "claude-desktop": json.loads(p["claude-desktop"].read_text())["mcpServers"],
        "gemini": json.loads(p["gemini"].read_text())["mcpServers"],
        "codex": tomllib.loads(p["codex"].read_text())["mcp_servers"],
        "goose": goose["extensions"],
        "opencode": json.loads(p["opencode"].read_text())["mcp"]["servers"],
    }


def test_install_with_key_writes_every_config_and_never_prints_the_key(sandbox: Path) -> None:
    p = seed(sandbox)
    result = run(sandbox, "--agents", "all", "--with-key", key=FAKE_KEY)
    assert result.returncode == 0, result.stderr
    assert FAKE_KEY not in result.stdout + result.stderr
    found = entries(p)
    for agent, servers in found.items():
        assert "other" in servers or "developer" in servers, agent
    assert found["claude-desktop"]["edi"] == {
        "command": SERVER,
        "args": [],
        "env": {"EDI_API_KEY": FAKE_KEY},
    }
    assert found["gemini"]["edi"]["env"] == {"EDI_API_KEY": FAKE_KEY}  # type: ignore[index]
    assert found["codex"]["edi"] == {
        "command": SERVER,
        "args": [],
        "env": {"EDI_API_KEY": FAKE_KEY},
    }
    assert found["goose"]["edi"]["cmd"] == SERVER  # type: ignore[index]
    assert found["goose"]["edi"]["envs"] == {"EDI_API_KEY": FAKE_KEY}  # type: ignore[index]
    assert found["opencode"]["edi"] == {
        "type": "local",
        "command": [SERVER],
        "environment": {"EDI_API_KEY": FAKE_KEY},
    }
    assert json.loads(p["gemini"].read_text())["theme"] == "dark"
    assert tomllib.loads(p["codex"].read_text())["model"] == "o4"
    for path in p.values():
        assert Path(f"{path}.bak").exists()
        assert path.stat().st_mode & 0o077 == 0  # holds the key: owner-only


def test_backups_of_key_bearing_files_stay_owner_only(sandbox: Path) -> None:
    p = seed(sandbox)
    for path in p.values():
        path.chmod(0o644)
    assert run(sandbox, "--agents", "all", "--with-key", key=FAKE_KEY).returncode == 0
    # Second run (env change) backs up the 0600 key-bearing file; then uninstall backs it up again.
    assert (
        run(sandbox, "--agents", "all", "--with-key", "--env", "X=1", key=FAKE_KEY).returncode == 0
    )
    for path in p.values():
        bak = Path(f"{path}.bak")
        assert FAKE_KEY in bak.read_text()
        assert bak.stat().st_mode & 0o077 == 0, bak
    assert run(sandbox, "--agents", "all", "--uninstall").returncode == 0
    for path in p.values():
        assert FAKE_KEY not in path.read_text()
        assert Path(f"{path}.bak").stat().st_mode & 0o077 == 0


def test_dry_run_writes_nothing_and_masks_the_key(sandbox: Path) -> None:
    result = run(sandbox, "--agents", "all", "--with-key", "--dry-run", key=FAKE_KEY)
    assert result.returncode == 0, result.stderr
    assert FAKE_KEY not in result.stdout + result.stderr
    assert '"EDI_API_KEY": "***"' in result.stdout
    assert not any(path.exists() for path in paths(sandbox).values())


def test_without_key_registers_no_env_and_says_dataone(sandbox: Path) -> None:
    p = paths(sandbox)
    result = run(sandbox, "--agents", "claude-desktop,codex", key=FAKE_KEY)
    assert result.returncode == 0, result.stderr
    assert "DataONE" in result.stdout
    desktop = json.loads(p["claude-desktop"].read_text())["mcpServers"]["edi"]
    assert desktop == {"command": SERVER, "args": []}
    assert FAKE_KEY not in p["codex"].read_text()


def test_rerun_is_idempotent_and_uninstall_removes_only_edi(sandbox: Path) -> None:
    p = seed(sandbox)
    assert run(sandbox, "--agents", "all").returncode == 0
    again = run(sandbox, "--agents", "all")
    assert again.returncode == 0, again.stderr
    assert again.stdout.count("already up to date") == len(p)
    removed = run(sandbox, "--agents", "all", "--uninstall")
    assert removed.returncode == 0, removed.stderr
    for agent, servers in entries(p).items():
        assert "edi" not in servers, agent
        assert servers, agent  # the unrelated entry is still there


def test_key_cannot_be_passed_on_the_command_line(sandbox: Path) -> None:
    for name in ("EDI_API_KEY", "EDI_MCP_EDI__API_KEY"):
        result = run(sandbox, "--agents", "codex", "--env", f"{name}={FAKE_KEY}")
        assert result.returncode == 2
        assert "--with-key" in result.stderr
    assert not paths(sandbox)["codex"].exists()


def test_with_key_needs_the_environment_or_a_terminal(sandbox: Path) -> None:
    result = run(sandbox, "--agents", "codex", "--with-key")
    assert result.returncode == 2
    assert "EDI_API_KEY" in result.stderr


def test_extra_env_and_unknown_agent(sandbox: Path) -> None:
    result = run(sandbox, "--agents", "codex,nope", "--env", "EDI_MCP_SERVER__LOG_LEVEL=debug")
    assert result.returncode == 1
    assert "unknown agent 'nope'" in result.stdout
    codex = tomllib.loads(paths(sandbox)["codex"].read_text())["mcp_servers"]["edi"]
    assert codex["env"] == {"EDI_MCP_SERVER__LOG_LEVEL": "debug"}


def test_help_lists_every_agent(sandbox: Path) -> None:
    result = run(sandbox, "--help")
    assert result.returncode == 0
    for agent in ("claude", "claude-desktop", "codex", "gemini", "goose", "opencode"):
        assert agent in result.stdout
    assert os.access(SCRIPT, os.X_OK)


STUB = """#!/bin/sh
printf '%s\\n' "$0 $*" >> "$STUB_LOG"
if [ "$2" = get ]; then exit "${STUB_GET_EXIT:-1}"; fi
echo "stored: $*"
"""


@pytest.mark.parametrize("registered", [False, True])
def test_agent_clis_get_the_key_in_env_args_and_their_output_is_masked(
    sandbox: Path, registered: bool
) -> None:
    log = sandbox / "argv.log"
    for cli in ("claude", "codex", "gemini"):
        stub = sandbox / "bin" / cli
        stub.write_text(STUB)
        stub.chmod(0o755)
    extra = {"STUB_LOG": str(log), "STUB_GET_EXIT": "0" if registered else "1"}
    result = run(
        sandbox, "--agents", "claude,codex,gemini", "--with-key", key=FAKE_KEY, extra=extra
    )
    assert result.returncode == 0, result.stderr
    assert FAKE_KEY not in result.stdout + result.stderr
    assert "stored:" in result.stdout  # the CLIs' own output is shown, masked
    calls = [line.split(" ", 1)[1] for line in log.read_text().splitlines()]
    adds = [c for c in calls if " add " in f" {c} "]
    key_env = f"EDI_API_KEY={FAKE_KEY}"
    assert f"mcp add --scope user edi -e {key_env} -- {SERVER}" in adds
    assert f"mcp add edi --env {key_env} -- {SERVER}" in adds
    assert f"mcp add --scope user --transport stdio -e {key_env} edi {SERVER}" in adds
    removes = [c for c in calls if c.startswith("mcp remove")]
    assert removes == (["mcp remove --scope user edi", "mcp remove edi"] if registered else [])
    assert not any(path.exists() for path in paths(sandbox).values())  # CLIs, not files


def test_agent_cli_uninstall(sandbox: Path) -> None:
    log = sandbox / "argv.log"
    for cli in ("claude", "codex", "gemini"):
        stub = sandbox / "bin" / cli
        stub.write_text(STUB)
        stub.chmod(0o755)
    result = run(
        sandbox, "--agents", "claude,codex,gemini", "--uninstall", extra={"STUB_LOG": str(log)}
    )
    assert result.returncode == 0, result.stderr
    calls = [line.split(" ", 1)[1] for line in log.read_text().splitlines()]
    assert calls == [
        "mcp remove --scope user edi",
        "mcp remove edi",
        "mcp remove --scope user edi",
    ]
