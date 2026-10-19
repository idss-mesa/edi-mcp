"""Confined, plan-before-transfer downloads (stdio only; DESIGN.md D17).

Ported from neon-mcp. Every destination resolves (symlinks included) under the
configured download directory; saved names match ``^[A-Za-z0-9._-]+$`` (EML
object names are sanitised, and the mapping is reported); every URL and
redirect hop must be on ``downloads.allowed_hosts``; the plan is checked
against the per-call file and byte caps before a byte moves; files stream to
``.part`` with a SHA-1 (what EDI publishes) and are moved into place with an
exclusive link, so an existing file is **never overwritten**: identical ones
are skipped, different ones reported as a conflict.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from edi_mcp.config import DownloadsConfig
from edi_mcp.errors import ToolError

BASENAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
FileStatus = Literal["downloaded", "skipped", "conflict", "failed"]


def safe_name(name: str, *, fallback: str = "entity") -> str:
    """A basename that matches :data:`BASENAME_RE` (spaces and the like become ``_``)."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _UNSAFE_RE.sub("_", base).strip("._") or fallback
    if cleaned in (".", ".."):
        cleaned = fallback
    return cleaned[:180]


def unique_names(names: list[str]) -> list[str]:
    """De-duplicate saved names: ``a.csv``, ``a-2.csv``, …"""
    seen: dict[str, int] = {}
    out = []
    for name in names:
        key = name.lower()
        if key not in seen:
            seen[key] = 1
            out.append(name)
            continue
        seen[key] += 1
        stem, dot, ext = name.rpartition(".")
        candidate = f"{stem}-{seen[key]}.{ext}" if dot and stem else f"{name}-{seen[key]}"
        seen[candidate.lower()] = 1
        out.append(candidate)
    return out


def sha1_of(path: Path) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class Written:
    path: Path
    bytes: int
    sha1: str
    seconds: float


class DownloadArea:
    """The download directory and its rules."""

    def __init__(self, config: DownloadsConfig) -> None:
        self.config = config

    @property
    def root(self) -> Path:
        return self.config.directory.expanduser().resolve()

    def clean_subdir(self, value: str | None) -> PurePosixPath:
        if not value:
            return PurePosixPath()
        if value.startswith(("/", "\\")) or "\\" in value or ":" in value:
            raise ToolError(
                "download_denied",
                "dest_subdir must be a relative path using '/'.",
                details={"destSubdir": value},
            )
        parts = [p for p in value.split("/") if p not in ("", ".")]
        if any(p == ".." or not BASENAME_RE.match(p) for p in parts):
            raise ToolError(
                "download_denied",
                "dest_subdir may contain only letters, digits, '.', '_', '-' and '/'.",
                details={"destSubdir": value},
            )
        return PurePosixPath(*parts)

    def destination(self, subdir: PurePosixPath, *parts: str) -> Path:
        """``parts`` under the root, refusing unsafe names, traversal and symlink escapes."""
        if not parts or not all(BASENAME_RE.match(p) and p not in (".", "..") for p in parts):
            raise ToolError("download_denied", f"Refusing an unsafe file name: {parts!r}.")
        root = self.root
        resolved = root.joinpath(*subdir.parts, *parts).resolve()
        if not resolved.is_relative_to(root):
            raise ToolError("download_denied", "Destination escapes the download directory.")
        return resolved

    def check_plan(self, count: int, known_bytes: int, max_bytes: int | None) -> int:
        """Raise ``download_limit_exceeded`` if the plan breaks a cap; returns the byte cap."""
        cfg = self.config
        cap = min(max_bytes, cfg.max_bytes_per_call) if max_bytes else cfg.max_bytes_per_call
        if count > cfg.max_files_per_call or known_bytes > cap:
            raise ToolError(
                "download_limit_exceeded",
                f"The plan has {count} file(s) and {known_bytes} known bytes; the limits are "
                f"{cfg.max_files_per_call} files and {cap} bytes per call.",
                details={
                    "files": count,
                    "bytes": known_bytes,
                    "maxFiles": cfg.max_files_per_call,
                    "maxBytes": cap,
                },
                hint="Pass fewer entities, or raise downloads.max_bytes_per_call.",
            )
        return cap

    @staticmethod
    def existing_matches(dest: Path, size: int | None, sha1: str | None) -> bool | None:
        """True when ``dest`` already holds this object, False when it holds something else,
        None when it does not exist."""
        if not dest.exists():
            return None
        if size is not None and dest.stat().st_size != size:
            return False
        if sha1:
            return sha1_of(dest) == sha1.lower()
        return size is not None

    async def write(
        self, chunks: AsyncIterator[bytes], dest: Path, *, max_bytes: int, label: str
    ) -> Written:
        """Stream to ``dest.part``, then link into place (never replacing a file)."""
        started = time.monotonic()
        partial = dest.with_name(dest.name + ".part")
        digest = hashlib.sha1(usedforsecurity=False)
        total = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with partial.open("wb") as handle:
                async for chunk in chunks:
                    total += len(chunk)
                    if total > max_bytes:
                        raise ToolError(
                            "download_limit_exceeded",
                            f"{label} exceeds the limit of {max_bytes} bytes; the partial file was removed.",
                            details={"file": dest.name, "maxBytes": max_bytes},
                        )
                    digest.update(chunk)
                    handle.write(chunk)
            try:
                os.link(partial, dest)  # exclusive: fails if dest appeared meanwhile
            except FileExistsError:
                raise ToolError(
                    "download_denied",
                    f"{dest.name} appeared while downloading; it was left untouched.",
                    details={"file": str(dest)},
                ) from None
            except OSError:
                # No hard links on this file system: rename, still refusing to replace.
                if dest.exists():
                    raise ToolError(
                        "download_denied", f"{dest.name} already exists; it was left untouched."
                    ) from None
                os.rename(partial, dest)
        finally:
            partial.unlink(missing_ok=True)
        return Written(dest, total, digest.hexdigest(), round(time.monotonic() - started, 3))


__all__ = [
    "BASENAME_RE",
    "DownloadArea",
    "FileStatus",
    "Written",
    "safe_name",
    "sha1_of",
    "unique_names",
]
