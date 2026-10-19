"""DownloadArea: names, confinement, caps and the never-overwrite write path."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath

import pytest

from edi_mcp.config import DownloadsConfig
from edi_mcp.edi.downloads import DownloadArea, safe_name, sha1_of, unique_names
from edi_mcp.errors import ToolError


def area(tmp_path: Path, **kw: object) -> DownloadArea:
    return DownloadArea(DownloadsConfig.model_validate({"directory": str(tmp_path), **kw}))


async def chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


def test_safe_and_unique_names() -> None:
    assert safe_name("My Data (2020).csv") == "My_Data_2020_.csv"
    assert safe_name("../../etc/passwd") == "passwd"
    assert safe_name("...") == "entity" and safe_name("", fallback="x") == "x"
    assert unique_names(["a.csv", "A.csv", "a.csv", "b"]) == ["a.csv", "A-2.csv", "a-3.csv", "b"]


def test_destination_refuses_escapes(tmp_path: Path) -> None:
    a = area(tmp_path)
    assert a.destination(PurePosixPath("x"), "f.csv") == (tmp_path / "x" / "f.csv").resolve()
    (tmp_path / "link").symlink_to(tmp_path.parent)
    with pytest.raises(ToolError) as err:
        a.destination(PurePosixPath("link"), "f.csv")
    assert err.value.code == "download_denied"
    with pytest.raises(ToolError):
        a.destination(PurePosixPath(), "..")


def test_plan_caps(tmp_path: Path) -> None:
    a = area(tmp_path, max_files_per_call=2, max_bytes_per_call=100)
    assert a.check_plan(2, 100, None) == 100
    assert a.check_plan(1, 10, 50) == 50
    for count, size, cap in ((3, 1, None), (1, 101, None), (1, 60, 50)):
        with pytest.raises(ToolError) as err:
            a.check_plan(count, size, cap)
        assert err.value.code == "download_limit_exceeded"


async def test_write_streams_hashes_and_never_replaces(tmp_path: Path) -> None:
    a = area(tmp_path)
    dest = tmp_path / "d" / "f.csv"
    written = await a.write(chunks(b"ab", b"c"), dest, max_bytes=10, label="f.csv")
    assert dest.read_bytes() == b"abc" and written.bytes == 3
    assert written.sha1 == sha1_of(dest) == "a9993e364706816aba3e25717850c26c9cd0d89d"
    assert a.existing_matches(dest, 3, written.sha1) is True
    assert a.existing_matches(dest, 4, None) is False
    assert a.existing_matches(tmp_path / "none", 3, None) is None
    with pytest.raises(ToolError) as err:
        await a.write(chunks(b"other"), dest, max_bytes=10, label="f.csv")
    assert err.value.code == "download_denied" and dest.read_bytes() == b"abc"
    assert not list(dest.parent.glob("*.part"))


async def test_write_stops_at_the_cap_and_removes_the_partial_file(tmp_path: Path) -> None:
    a = area(tmp_path)
    dest = tmp_path / "big.zip"
    with pytest.raises(ToolError) as err:
        await a.write(chunks(b"x" * 6, b"x" * 6), dest, max_bytes=10, label="big.zip")
    assert err.value.code == "download_limit_exceeded" and "partial file" in err.value.message
    assert not dest.exists() and not list(tmp_path.glob("*.part"))


def test_clean_subdir(tmp_path: Path) -> None:
    a = area(tmp_path)
    assert a.clean_subdir("a/./b/") == PurePosixPath("a/b")
    assert a.clean_subdir(None) == PurePosixPath()
    for bad in ("/a", "a\\b", "c:x", "a/../b", "a b"):
        with pytest.raises(ToolError):
            a.clean_subdir(bad)
