from __future__ import annotations

import json
from importlib.metadata import entry_points

import pytest

import edi_mcp
from edi_mcp import __main__ as cli


def test_version_and_entry_point() -> None:
    assert edi_mcp.__version__ == "0.1.0"
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts")}
    assert scripts.get("edi-mcp") == "edi_mcp.__main__:main"


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "edi-mcp 0.1.0" in capsys.readouterr().out


def test_print_config_redacts_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EDI_API_KEY", "cli-secret-key-1234")
    assert cli.main(["--print-config", "--transport", "http", "--no-downloads"]) == 0
    out = capsys.readouterr().out
    assert "cli-secret-key-1234" not in out
    assert "api_key: '***'" in out
    assert "transport: http" in out


def test_check_without_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("EDI_API_KEY", raising=False)
    monkeypatch.delenv("EDI_MCP_EDI__API_KEY", raising=False)
    assert cli.main(["--check", "--log-level", "error"]) == 0
    report = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert report == {
        "ok": True,
        "version": "0.1.0",
        "protocolVersion": "2026-07-28",
        "transport": "stdio",
        "keyConfigured": False,
        "backend": "dataone",
    }


def test_check_with_key_never_prints_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("EDI_API_KEY", "cli-secret-key-5678")
    assert cli.main(["--check", "--log-level", "debug"]) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out.strip().splitlines()[-1])
    assert report["keyConfigured"] is True and report["backend"] == "pasta"
    assert "cli-secret-key-5678" not in captured.out + captured.err
