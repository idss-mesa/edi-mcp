"""``edi-mcp`` command line.

Flags > environment (``EDI_MCP_*``, plus ``EDI_API_KEY``) > YAML (``--config``)
> defaults. There is deliberately no ``--key`` flag: keys on a command line
leak into ``ps`` output and shell history.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from edi_mcp import __version__

if TYPE_CHECKING:
    from edi_mcp.config import Config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edi-mcp",
        description="MCP (2026-07-28) server for the EDI data repository. Bare `edi-mcp` serves stdio.",
    )
    parser.add_argument("--config", type=Path, default=None, help="YAML config file.")
    parser.add_argument(
        "--transport", choices=("stdio", "http"), default=None, help="Transport (default stdio)."
    )
    parser.add_argument(
        "--bind-address", default=None, help="HTTP bind address (default 127.0.0.1)."
    )
    parser.add_argument(
        "--bind-port", type=int, default=None, help="HTTP bind port (default 8080)."
    )
    parser.add_argument(
        "--log-level", choices=("debug", "info", "warning", "error", "critical"), default=None
    )
    parser.add_argument(
        "--download-dir", type=Path, default=None, help="Directory downloads are confined to."
    )
    parser.add_argument("--no-downloads", action="store_true", help="Disable the download tools.")
    parser.add_argument(
        "--print-config", action="store_true", help="Print the effective config (key redacted)."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Load config, call edi_ping in-process, print a JSON report, exit 0/1.",
    )
    parser.add_argument("--version", action="version", version=f"edi-mcp {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from edi_mcp.config import load_config, set_active_config
    from edi_mcp.logging import setup_logging

    overrides = {
        "transport": args.transport,
        "bind_address": args.bind_address,
        "bind_port": args.bind_port,
        "log_level": args.log_level,
        "download_dir": str(args.download_dir) if args.download_dir else None,
        "downloads_enabled": False if args.no_downloads else None,
    }
    config = load_config(args.config, flag_overrides=overrides)
    set_active_config(config)

    if args.print_config:
        import yaml

        yaml.safe_dump(config.model_dump_redacted(), sys.stdout, sort_keys=False)
        return 0

    setup_logging(config.server.log_level, transport=config.server.transport)
    if args.check:
        import asyncio

        return asyncio.run(_check(config))

    from edi_mcp.server import run

    run(config, transport=config.server.transport)
    return 0


async def _check(config: Config) -> int:
    import json

    from edi_mcp.server import create_server

    server = create_server(config, transport=config.server.transport)
    try:
        outcome = await server.call("edi_ping", {})
    finally:
        await server.aclose()
    payload = outcome.payload
    report: dict[str, Any] = {
        "ok": not outcome.is_error,
        "version": __version__,
        "protocolVersion": payload.get("protocolVersion"),
        "transport": payload.get("transport"),
        "keyConfigured": payload.get("keyConfigured"),
        "backend": payload.get("backend"),
    }
    if outcome.is_error:
        report["problem"] = (payload.get("error") or {}).get("message")
    print(json.dumps(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
