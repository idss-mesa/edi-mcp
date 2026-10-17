"""Configuration model and loader for edi-mcp.

Precedence (highest wins): CLI flag > environment variable > YAML file > default.

Environment variables use the ``EDI_MCP_`` prefix and ``__`` to descend into
nested sections at any depth: ``EDI_MCP_EDI__RETRIES__MAX_ATTEMPTS`` sets
``config.edi.retries.max_attempts``. List fields accept a comma-separated
string. The EDI API key (``EDI_MCP_EDI__API_KEY``) additionally falls back to
``EDI_API_KEY``, the name EDI's own guides and EDIutils use. Look-alike names
(``EDI_KEY``, ``EDI_TOKEN``, ``EDI_AUTH_TOKEN``) are not read; the loader warns
when one is set without ``EDI_API_KEY`` (DESIGN.md D5).

The loader validates shape only; it never contacts EDI.
"""

from __future__ import annotations

import logging
import os
import types as _pytypes
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

logger = logging.getLogger(__name__)

Transport = Literal["stdio", "http"]
LogLevel = Literal["debug", "info", "warning", "error", "critical"]

ENV_PREFIX = "EDI_MCP_"
ENV_DELIM = "__"
#: Key variables consulted, in order, when EDI_MCP_EDI__API_KEY is unset.
KEY_ENV_FALLBACKS: tuple[str, ...] = ("EDI_API_KEY",)
#: Plausible-looking variables that are *not* read (warned about when alone).
IGNORED_KEY_ENV: tuple[str, ...] = ("EDI_KEY", "EDI_TOKEN", "EDI_AUTH_TOKEN")


class _Section(BaseModel):
    # Unknown keys are warned about by the loader, not rejected: failing to
    # start over a stale key is worse than running with a documented default.
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


class RetryConfig(_Section):
    """Retry policy for 429, 5xx and network failures (every read is idempotent)."""

    max_attempts: int = Field(
        3, ge=1, le=10, description="Attempts per upstream call, including the first."
    )
    backoff_base_s: float = Field(
        0.5, ge=0, description="Base of the exponential backoff (0.5 * 2^n seconds)."
    )
    backoff_max_s: float = Field(8.0, ge=0, description="Cap on a single backoff sleep.")
    retry_after_default_s: float = Field(
        1.0, ge=0, description="Wait used on HTTP 429 when no Retry-After header is sent."
    )


class EdiConfig(_Section):
    """Upstream EDI (PASTA+), IAM, DataONE and citation-service settings."""

    pasta_base_url: str = Field(
        "https://pasta.lternet.edu", description="PASTA+ base URL (package and audit services)."
    )
    auth_base_url: str = Field(
        "https://auth.edirepository.org/auth/v1",
        description="EDI Identity and Access Manager API (key -> edi-token exchange).",
    )
    dataone_cn_url: str = Field(
        "https://cn.dataone.org/cn/v2",
        description="DataONE coordinating node (Solr search, resolve) used without a key.",
    )
    gmn_lter_url: str = Field(
        "https://gmn.lternet.edu/mn/v2",
        description="DataONE member node serving knb-lter-* packages without a key.",
    )
    gmn_edi_url: str = Field(
        "https://gmn.edirepository.org/mn/v2",
        description="DataONE member node serving edi.* and other non-LTER packages without a key.",
    )
    cite_url: str = Field(
        "https://cite.edirepository.org/cite", description="EDI citation service (anonymous)."
    )
    portal_url: str = Field(
        "https://portal.edirepository.org/nis",
        description="EDI Data Portal (landing pages are built from it).",
    )
    api_key: SecretStr | None = Field(
        None,
        description="EDI API access key (https://auth.edirepository.org/auth/ui/key). Enables the "
        "PASTA backend; without it edi-mcp uses DataONE. Prefer the EDI_API_KEY env var; never commit it.",
    )
    user_agent_suffix: str | None = Field(
        None, description="Text appended to the User-Agent header."
    )
    connect_timeout_s: float = Field(10.0, gt=0, description="TCP/TLS connect timeout.")
    read_timeout_s: float = Field(60.0, gt=0, description="Default read timeout.")
    download_read_timeout_s: float = Field(
        300.0, gt=0, description="Read timeout for data-entity downloads."
    )
    max_concurrency: int = Field(
        4, ge=1, le=32, description="Maximum simultaneous upstream requests."
    )
    retries: RetryConfig = Field(default_factory=RetryConfig)


class CacheTTLs(_Section):
    """Time-to-live, in seconds, per cache family."""

    listings: int = Field(3600, ge=0, description="Scope, identifier and revision listings.")
    search: int = Field(600, ge=0, description="Search results.")
    metadata: int = Field(
        86400, ge=0, description="EML and entity facts of a given revision (immutable upstream)."
    )
    reports: int = Field(86400, ge=0, description="Quality reports and provenance.")
    feeds: int = Field(300, ge=0, description="Change and upload feeds, read counts.")
    citations: int = Field(86400, ge=0, description="Formatted citations.")


class CacheConfig(_Section):
    """In-process response cache."""

    enabled: bool = Field(True, description="Cache upstream responses in memory.")
    max_entries: int = Field(1024, ge=1, description="Overall entry cap across families.")
    stale_if_error_s: int = Field(
        86400, ge=0, description="How long an expired entry may be served when a refresh fails."
    )
    ttl_s: CacheTTLs = Field(default_factory=CacheTTLs)


class LimitsConfig(_Section):
    """Result-size and request-shape limits."""

    default_limit: int = Field(
        25, ge=1, description="Default page size where a tool does not set its own."
    )
    max_limit: int = Field(200, ge=1, description="Largest page size any tool accepts.")
    max_result_bytes: int = Field(
        50_000,
        ge=1000,
        description="Tool results are trimmed (with page.truncated) to fit this many bytes of compact JSON.",
    )
    hard_max_result_bytes: int = Field(
        200_000,
        ge=1000,
        description="A result still larger than this after trimming fails with result_too_large.",
    )
    text_budget_summary: int = Field(
        300, ge=40, description="Characters kept of long text fields (abstracts) in summaries."
    )
    text_budget_detail: int = Field(
        4000, ge=100, description="Default characters kept of long text fields in detail views."
    )
    max_eml_bytes: int = Field(
        20 * 1024 * 1024,
        ge=1024,
        description="Largest EML document parsed (larger ones fail with result_too_large).",
    )
    preview_max_bytes: int = Field(
        256 * 1024, ge=1024, description="Most bytes edi_preview_entity reads from an entity."
    )
    tools_list_max_bytes: int = Field(
        60_000,
        ge=1000,
        description="Conformance bound on the serialized tools/list result; tightened once every tool lands.",
    )


class DownloadsConfig(_Section):
    """Local downloads (stdio only)."""

    enabled: bool | None = Field(
        None,
        description="Offer the download tools. Unset: true on stdio; never available over http.",
    )
    directory: Path = Field(
        Path("~/edi-downloads"),
        validate_default=True,
        description="Directory every download is confined to (created on first use).",
    )
    max_files_per_call: int = Field(
        50, ge=1, description="Most entities one edi_download_entities call transfers."
    )
    max_bytes_per_call: int = Field(
        2 * 1024**3, ge=1, description="Most bytes one download call transfers."
    )
    max_file_bytes: int = Field(1024**3, ge=1, description="Largest single file accepted.")
    verify_checksums: bool = Field(True, description="Verify the SHA-1 checksums EDI publishes.")
    allowed_hosts: list[str] = Field(
        default_factory=lambda: [
            "pasta.lternet.edu",
            "gmn.lternet.edu",
            "gmn.edirepository.org",
            "cn.dataone.org",
        ],
        description="Hosts downloads (and their redirects) may come from; '*.' is a subdomain wildcard.",
    )

    @field_validator("directory", mode="after")
    @classmethod
    def _expand(cls, value: Path) -> Path:
        return value.expanduser().resolve()


class ServerConfig(_Section):
    """Transport, HTTP binding and per-request key handling."""

    transport: Transport = Field(
        "stdio", description="stdio (local clients) or http (stateless Streamable HTTP at /mcp)."
    )
    bind_address: str = Field("127.0.0.1", description="HTTP bind address.")
    bind_port: int = Field(8080, ge=1, le=65535, description="HTTP bind port.")
    public_base_url: str | None = Field(
        None,
        description="Public URL of a hosted deployment; its host/origin join the allow-lists and "
        "https:// enables per-request keys.",
    )
    allowed_hosts: list[str] = Field(
        default_factory=list, description="Host header allow-list (DNS-rebinding protection)."
    )
    allowed_origins: list[str] = Field(
        default_factory=list, description="Origin header allow-list (DNS-rebinding protection)."
    )
    dns_rebinding_protection: bool | None = Field(
        None,
        description="Force DNS-rebinding protection on/off. "
        "Unset: SDK default (on for loopback binds or when allow-lists are set).",
    )
    json_response: bool = Field(
        False, description="Answer POST /mcp with application/json instead of a single SSE frame."
    )
    max_request_body_size: int = Field(
        1024 * 1024, ge=1024, description="Largest accepted request body in bytes."
    )
    accept_header_key: bool = Field(
        True, description="HTTP: honour a per-request EDI API key header (subject to the TLS gate)."
    )
    request_key_header: str = Field(
        "X-EDI-Key", description="Header carrying a caller's EDI API key in HTTP mode."
    )
    allow_insecure_header_key: bool = Field(
        False,
        description="Accept header keys when public_base_url is not https:// (development only).",
    )
    share_config_key_over_http: bool = Field(
        False,
        description="Lend the operator's configured key to HTTP callers without one (private deployments only).",
    )
    tools_list_ttl_ms: int = Field(300_000, ge=0, description="ttlMs advertised on tools/list.")
    log_level: LogLevel = Field("info", description="Log verbosity.")
    instructions_extra: str | None = Field(
        None, description="Text appended to the server instructions."
    )


class Config(BaseModel):
    """Root configuration object."""

    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    edi: EdiConfig = Field(default_factory=EdiConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    downloads: DownloadsConfig = Field(default_factory=DownloadsConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    def model_dump_redacted(self) -> dict[str, Any]:
        """JSON-safe dump with the key replaced by ``***`` (for --print-config)."""
        data = self.model_dump(mode="json")
        data["edi"]["api_key"] = "***" if self.edi.api_key is not None else None
        return data

    def key_value(self) -> str | None:
        """The configured API key in clear, or ``None`` (never log the result)."""
        if self.edi.api_key is None:
            return None
        value = self.edi.api_key.get_secret_value().strip()
        return value or None

    def effective_downloads_enabled(self, transport: str) -> bool:
        """Downloads exist only on stdio, and only unless explicitly disabled."""
        return transport == "stdio" and self.downloads.enabled is not False


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _coerce_env_value(raw: str) -> Any:
    """Env values stay strings (pydantic coerces them); null-ish become ``None``."""
    if raw.strip().lower() in {"", "null", "none"}:
        return None
    return raw


def _deep_merge(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config file {path} must contain a YAML mapping at the top level.")
    return data


def _load_env(env: Mapping[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, raw in env.items():
        if not key.startswith(ENV_PREFIX):
            continue
        parts = [p.lower() for p in key[len(ENV_PREFIX) :].split(ENV_DELIM) if p]
        if not parts:
            continue
        cursor: dict[str, Any] = out
        conflict = False
        for part in parts[:-1]:
            nxt = cursor.setdefault(part, {})
            if not isinstance(nxt, dict):
                conflict = True
                break
            cursor = nxt
        if not conflict:
            cursor[parts[-1]] = _coerce_env_value(raw)
    return out


def _unwrap_optional(annotation: Any) -> list[Any]:
    origin = get_origin(annotation)
    if origin in (Union, _pytypes.UnionType):
        return [a for a in get_args(annotation) if a is not type(None)]
    return [annotation]


def _is_list(annotation: Any) -> bool:
    return any(get_origin(a) is list for a in _unwrap_optional(annotation))


def _submodel(annotation: Any) -> type[BaseModel] | None:
    for a in _unwrap_optional(annotation):
        if isinstance(a, type) and issubclass(a, BaseModel):
            return a
    return None


def _normalize_lists(data: dict[str, Any], model: type[BaseModel]) -> None:
    """Split comma-separated strings destined for list fields (env convenience)."""
    for name, field in model.model_fields.items():
        if name not in data:
            continue
        value = data[name]
        if isinstance(value, str) and _is_list(field.annotation):
            data[name] = [p.strip() for p in value.split(",") if p.strip()]
        elif isinstance(value, dict):
            sub = _submodel(field.annotation)
            if sub is not None:
                _normalize_lists(value, sub)


def _warn_unknown_keys(
    layer: Mapping[str, Any], model: type[BaseModel] = Config, *, source: str, prefix: str = ""
) -> list[str]:
    """Log (and return) dotted keys no model field consumes."""
    unknown: list[str] = []
    for key, value in layer.items():
        dotted = f"{prefix}{key}"
        field = model.model_fields.get(key)
        if field is None:
            unknown.append(dotted)
            logger.warning(
                "config: unknown key %r from %s ignored (check spelling)", dotted, source
            )
            continue
        sub = _submodel(field.annotation)
        if sub is not None and isinstance(value, dict):
            unknown.extend(_warn_unknown_keys(value, sub, source=source, prefix=f"{dotted}."))
    return unknown


_FLAG_PATHS: dict[str, tuple[str, str]] = {
    "transport": ("server", "transport"),
    "bind_address": ("server", "bind_address"),
    "bind_port": ("server", "bind_port"),
    "log_level": ("server", "log_level"),
    "download_dir": ("downloads", "directory"),
    "downloads_enabled": ("downloads", "enabled"),
}


def _flags_to_layer(flag_overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    layer: dict[str, Any] = {}
    for key, value in (flag_overrides or {}).items():
        if value is None:
            continue
        if key not in _FLAG_PATHS:
            raise KeyError(f"unknown flag override {key!r}")
        section, field = _FLAG_PATHS[key]
        layer.setdefault(section, {})[field] = value
    return layer


def load_config(
    path: Path | None = None,
    *,
    flag_overrides: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> Config:
    """Load configuration with precedence flag > env > YAML > defaults."""
    source_env = os.environ if env is None else env
    yaml_layer = _load_yaml(path) if path is not None else {}
    env_layer = _load_env(source_env)
    flag_layer = _flags_to_layer(flag_overrides)

    _warn_unknown_keys(yaml_layer, source="config file")
    _warn_unknown_keys(env_layer, source="environment")

    merged = _deep_merge(_deep_merge(yaml_layer, env_layer), flag_layer)
    edi = merged.get("edi")
    if not (isinstance(edi, dict) and edi.get("api_key")):
        for name in KEY_ENV_FALLBACKS:
            value = source_env.get(name, "").strip()
            if value:
                merged.setdefault("edi", {})
                if isinstance(merged["edi"], dict):
                    merged["edi"]["api_key"] = value
                break
    edi = merged.get("edi")
    if not (isinstance(edi, dict) and edi.get("api_key")):
        for name in IGNORED_KEY_ENV:
            if source_env.get(name, "").strip():
                logger.warning(
                    "%s is set but edi-mcp does not read it; rename it to EDI_API_KEY", name
                )
    _normalize_lists(merged, Config)
    return Config.model_validate(merged)


# ---------------------------------------------------------------------------
# Process-wide active config
# ---------------------------------------------------------------------------

_active_config: Config | None = None


def set_active_config(config: Config | None) -> None:
    """Record (or clear) the resolved config; called by the CLI entry point."""
    global _active_config
    _active_config = config


def get_active_config() -> Config:
    """The config set by the entry point, or env + defaults when none was set."""
    return _active_config if _active_config is not None else load_config()
