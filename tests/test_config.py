from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from edi_mcp.config import Config, get_active_config, load_config, set_active_config


def test_defaults_and_effective_values() -> None:
    cfg = load_config(env={})
    assert cfg.server.transport == "stdio"
    assert cfg.edi.api_key is None and cfg.key_value() is None
    assert cfg.edi.pasta_base_url == "https://pasta.lternet.edu"
    assert cfg.edi.auth_base_url == "https://auth.edirepository.org/auth/v1"
    assert cfg.server.request_key_header == "X-EDI-Key"
    assert cfg.limits.max_result_bytes == 50_000
    assert cfg.effective_downloads_enabled("stdio") and not cfg.effective_downloads_enabled("http")


def test_precedence_flag_over_env_over_yaml(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text(
        "server:\n  bind_port: 9000\n  log_level: debug\nlimits:\n  max_result_bytes: 30000\n"
    )
    cfg = load_config(
        path, env={"EDI_MCP_SERVER__BIND_PORT": "9100"}, flag_overrides={"log_level": "error"}
    )
    assert cfg.server.bind_port == 9100
    assert cfg.server.log_level == "error"
    assert cfg.limits.max_result_bytes == 30_000


def test_env_nesting_lists_and_nulls() -> None:
    cfg = load_config(
        env={
            "EDI_MCP_EDI__RETRIES__MAX_ATTEMPTS": "5",
            "EDI_MCP_CACHE__TTL_S__SEARCH": "60",
            "EDI_MCP_SERVER__ALLOWED_HOSTS": "a.example, b.example",
            "EDI_MCP_DOWNLOADS__ENABLED": "false",
            "EDI_MCP_SERVER__PUBLIC_BASE_URL": "none",
        }
    )
    assert cfg.edi.retries.max_attempts == 5
    assert cfg.cache.ttl_s.search == 60
    assert cfg.server.allowed_hosts == ["a.example", "b.example"]
    assert cfg.downloads.enabled is False
    assert cfg.server.public_base_url is None
    assert not cfg.effective_downloads_enabled("stdio")


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"EDI_API_KEY": "key-aaaa"}, "key-aaaa"),
        ({"EDI_TOKEN": "key-bbbb"}, None),  # look-alike names are ignored (DESIGN.md D5)
        ({"EDI_KEY": "key-bbbb"}, None),
        ({"EDI_API_KEY": "key-aaaa", "EDI_TOKEN": "key-bbbb"}, "key-aaaa"),
        ({"EDI_MCP_EDI__API_KEY": "key-cccc", "EDI_API_KEY": "key-aaaa"}, "key-cccc"),
        ({"EDI_MCP_EDI__API_KEY": "   "}, None),
        ({"EDI_API_KEY": "  key-dddd \n"}, "key-dddd"),
        ({}, None),
    ],
)
def test_key_env_fallbacks(env: dict[str, str], expected: str | None) -> None:
    assert load_config(env=env).key_value() == expected


def test_yaml_key_beats_fallback_env(tmp_path: Path) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("edi:\n  api_key: yaml-key-1234\n")
    assert load_config(path, env={"EDI_API_KEY": "env-key-1234"}).key_value() == "yaml-key-1234"


def test_key_never_rendered() -> None:
    cfg = load_config(env={"EDI_API_KEY": "secret-key-value"})
    assert "secret-key-value" not in repr(cfg)
    dumped = cfg.model_dump_redacted()
    assert dumped["edi"]["api_key"] == "***"
    assert "secret-key-value" not in str(dumped)


def test_unknown_keys_warn(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "c.yaml"
    path.write_text("edi:\n  bogus: 1\nnope: {}\ncache:\n  ttl_s:\n    nada: 5\n")
    with caplog.at_level(logging.WARNING, logger="edi_mcp.config"):
        load_config(path, env={"EDI_MCP_SERVER__NOPE": "1"})
    text = caplog.text
    for key in ("edi.bogus", "'nope'", "cache.ttl_s.nada", "server.nope"):
        assert key in text


def test_download_dir_is_expanded() -> None:
    cfg = load_config(env={}, flag_overrides={"download_dir": "~/edi-x"})
    assert cfg.downloads.directory.is_absolute()
    assert "~" not in str(cfg.downloads.directory)
    assert load_config(env={}).downloads.directory.is_absolute()


def test_invalid_values_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        load_config(env={"EDI_MCP_SERVER__TRANSPORT": "sse"})
    path = tmp_path / "c.yaml"
    path.write_text("- not\n- a mapping\n")
    with pytest.raises(ValueError, match="mapping"):
        load_config(path, env={})
    with pytest.raises(KeyError):
        load_config(env={}, flag_overrides={"key": "x"})


def test_active_config_roundtrip() -> None:
    cfg = Config()
    set_active_config(cfg)
    try:
        assert get_active_config() is cfg
    finally:
        set_active_config(None)
    assert isinstance(get_active_config(), Config)


def test_lookalike_key_alone_warns_without_leaking(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="edi_mcp.config"):
        cfg = load_config(env={"EDI_TOKEN": "key-bbbb-secret"})
    assert cfg.key_value() is None
    assert "rename it to EDI_API_KEY" in caplog.text
    assert "key-bbbb-secret" not in caplog.text
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="edi_mcp.config"):
        load_config(env={"EDI_API_KEY": "key-aaaa", "EDI_TOKEN": "key-bbbb"})
    assert "EDI_TOKEN" not in caplog.text
