"""Preview and download tools on both backends, replayed from recorded fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from edi_mcp.server import EdiServer
from tests.fixture_router import FixtureRouter, Reply
from tests.helpers import TEST_KEY, call_err, call_ok

HBR = "knb-lter-hbr.14.22"
THIESSEN = "c4f72fa0cb155f1b61f1333bb67e3d00"
PASTA_DATA = f"GET pasta.lternet.edu/package/data/eml/knb-lter-hbr/14/22/{THIESSEN}"
ZIP = "GET pasta.lternet.edu/package/download/eml/knb-lter-hbr/14/22"


@pytest.fixture(params=["pasta", "dataone"])
def either(request: pytest.FixtureRequest, server: EdiServer, key_server: EdiServer) -> EdiServer:
    return key_server if request.param == "pasta" else server


def _backend(server: EdiServer) -> str:
    return "pasta" if server.config.key_value() else "dataone"


# ---------------------------------------------------------------------- edi_preview_entity


async def test_preview_detects_the_header_and_stops(either: EdiServer) -> None:
    p = await call_ok(
        either, "edi_preview_entity", {"package": HBR, "entity": "thiessen_weights", "rows": 5}
    )
    assert p["entityId"] == THIESSEN and p["name"] == "thiessen_weights" and p["size"] == 734
    assert p["columns"][:3] == ["SRG_Num", "WS_1", "WS_2"] and len(p["columns"]) == 10
    assert p["columnsFrom"] == "header"
    assert len(p["rows"]) == 5 and p["rows"][0][:3] == ["SRG-1", "0.1", "0.02"]
    assert p["complete"] is False and 0 < p["bytesRead"] <= 734
    assert any("header-line count" in n for n in p["notes"])
    assert p["source"]["backend"] == _backend(either)
    assert any("edi_download_entities" in s for s in p["nextSteps"])


async def test_preview_by_file_name_shows_every_row_when_asked(key_server: EdiServer) -> None:
    p = await call_ok(
        key_server,
        "edi_preview_entity",
        {"package": HBR, "entity": "THIESSEN_WEIGHTS", "rows": 200},
    )
    assert p["complete"] is True and p["bytesRead"] == 734
    assert all(len(r) == 10 for r in p["rows"])


async def test_preview_refuses_binary(key_server: EdiServer, router: FixtureRouter) -> None:
    router.add(PASTA_DATA, Reply(200, b"PK\x03\x04\x00\x00binary", "application/zip"))
    error = await call_err(
        key_server, "edi_preview_entity", {"package": HBR, "entity": THIESSEN}, "invalid_argument"
    )
    assert "binary" in error["message"] and "edi_download_entities" in error["hint"]


async def test_preview_cuts_long_cells(key_server: EdiServer, router: FixtureRouter) -> None:
    body = b"SRG_Num,WS_1\nSRG-1," + b"x" * 300 + b"\n"
    router.add(PASTA_DATA, Reply(200, body, "text/csv"))
    p = await call_ok(key_server, "edi_preview_entity", {"package": HBR, "entity": THIESSEN})
    assert p["columns"] == ["SRG_Num", "WS_1"] and p["complete"] is True
    assert len(p["rows"][0][1]) == 200 and p["rows"][0][1].endswith("…")
    assert any("cut to 200" in n for n in p["notes"])


async def test_preview_unknown_entity(either: EdiServer) -> None:
    error = await call_err(
        either, "edi_preview_entity", {"package": HBR, "entity": "nope"}, "not_found"
    )
    assert "edi_list_entities" in error["hint"]


async def test_unreplicated_scope_needs_a_key_before_any_request(
    server: EdiServer, router: FixtureRouter
) -> None:
    for tool, args in (
        ("edi_preview_entity", {"package": "icarus.13.1", "entity": "x"}),
        ("edi_download_entities", {"package": "icarus.13.1"}),
        ("edi_get_quality_report", {"package": "icarus.13.1"}),
    ):
        error = await call_err(server, tool, args, "auth_required")
        assert "icarus" in error["message"] and "EDI_API_KEY" in error["hint"]
    assert router.calls == []


# ---------------------------------------------------------------------- edi_download_entities


def _download_dir(server: EdiServer) -> Path:
    return server.config.downloads.directory


async def test_download_saves_verifies_and_skips_on_rerun(either: EdiServer) -> None:
    args = {"package": HBR, "entities": ["thiessen_weights"]}
    p = await call_ok(either, "edi_download_entities", args)
    folder = _download_dir(either) / HBR
    assert p["directory"] == str(folder) and p["downloaded"] == 1 and p["bytes"] == 734
    meta, data = p["files"]
    assert meta["name"] == "metadata (EML)" and meta["status"] == "downloaded"
    assert (folder / f"{HBR}.xml").read_bytes().startswith(b"<?xml")
    assert data["entityId"] == THIESSEN and data["status"] == "downloaded"
    assert data["sha1Verified"] is True and data["path"] == str(folder / "thiessen_weights.csv")
    saved = (folder / "thiessen_weights.csv").read_bytes()
    assert len(saved) == 734 and saved.startswith(b"SRG_Num,WS_1")
    again = await call_ok(either, "edi_download_entities", args)
    assert [f["status"] for f in again["files"]] == ["skipped", "skipped"]
    assert again["downloaded"] == 0 and again["bytes"] == 0
    assert not list(folder.glob("*.part"))


async def test_download_never_overwrites_a_different_file(key_server: EdiServer) -> None:
    folder = _download_dir(key_server) / HBR
    folder.mkdir(parents=True)
    (folder / "thiessen_weights.csv").write_text("mine")
    p = await call_ok(
        key_server,
        "edi_download_entities",
        {"package": HBR, "entities": [THIESSEN], "include_metadata": False},
    )
    (data,) = p["files"]
    assert data["status"] == "conflict" and "not overwritten" in data["error"]
    assert (folder / "thiessen_weights.csv").read_text() == "mine"
    assert any("dest_subdir" in n for n in p["notes"])


async def test_download_removes_a_file_whose_sha1_differs(
    key_server: EdiServer, router: FixtureRouter
) -> None:
    router.add(PASTA_DATA, Reply(200, b"tampered,data\n", "text/csv"))
    p = await call_ok(
        key_server,
        "edi_download_entities",
        {"package": HBR, "entities": [THIESSEN], "dest_subdir": "check"},
    )
    data = p["files"][-1]
    assert data["status"] == "failed" and data["sha1Verified"] is False
    assert data["error"].startswith("checksum_mismatch")
    assert not Path(data["path"]).exists() and p["downloaded"] == 0


async def test_download_refuses_a_redirect_off_the_allow_list(
    key_server: EdiServer, router: FixtureRouter
) -> None:
    router.add(PASTA_DATA, Reply(302, b"", headers={"location": "https://evil.example.org/x"}))
    p = await call_ok(key_server, "edi_download_entities", {"package": HBR, "entities": [THIESSEN]})
    data = p["files"][-1]
    assert data["status"] == "failed" and data["error"].startswith("upstream_error")


async def test_download_plan_caps_and_unsafe_subdirs(key_server: EdiServer) -> None:
    error = await call_err(
        key_server,
        "edi_download_entities",
        {"package": HBR, "entities": [THIESSEN], "max_bytes": 100},
        "download_limit_exceeded",
    )
    assert error["details"]["bytes"] == 734
    for subdir in ("../escape", "/abs", "a\\b", "ok/../../x"):
        await call_err(
            key_server,
            "edi_download_entities",
            {"package": HBR, "dest_subdir": subdir},
            "download_denied",
        )


async def test_download_tools_exist_only_on_stdio(make_server) -> None:  # type: ignore[no-untyped-def]
    http = make_server(transport="http", key=TEST_KEY)
    names = {t.name for t in http.tool_definitions()}
    assert "edi_download_entities" not in names and "edi_download_package" not in names
    assert "edi_preview_entity" in names


async def test_downloads_can_be_disabled_on_stdio(make_server, config) -> None:  # type: ignore[no-untyped-def]
    cfg = config.model_copy(deep=True)
    cfg.downloads.enabled = False
    stdio = make_server(config=cfg)
    assert "edi_download_entities" not in {t.name for t in stdio.tool_definitions()}


# ---------------------------------------------------------------------- edi_download_package


async def test_download_package_zip(key_server: EdiServer, router: FixtureRouter) -> None:
    body = b"PK\x03\x04" + b"z" * 100
    router.add(ZIP, Reply(200, body, "application/zip"))
    p = await call_ok(key_server, "edi_download_package", {"package": HBR})
    (saved,) = p["files"]
    assert saved["status"] == "downloaded" and saved["bytes"] == len(body)
    path = Path(saved["path"])
    assert path == _download_dir(key_server) / f"{HBR}.zip" and path.read_bytes() == body
    again = await call_ok(key_server, "edi_download_package", {"package": HBR})
    assert again["files"][0]["status"] == "skipped" and again["bytes"] == 0


async def test_download_package_caps(key_server: EdiServer, router: FixtureRouter) -> None:
    known = (await call_ok(key_server, "edi_get_package", {"package": HBR}))["totalBytes"]
    # The plan check refuses a cap below the package's known entity bytes...
    error = await call_err(
        key_server,
        "edi_download_package",
        {"package": HBR, "max_bytes": 10},
        "download_limit_exceeded",
    )
    assert error["details"]["maxBytes"] == 10
    # ...and an archive whose Content-Length exceeds the cap is refused before writing.
    router.add(ZIP, Reply(200, b"z" * (known + 5000), "application/zip"))
    error = await call_err(
        key_server,
        "edi_download_package",
        {"package": HBR, "max_bytes": known + 10},
        "download_limit_exceeded",
    )
    assert "above the limit" in error["message"] and "edi_download_entities" in error["hint"]
    assert not list(_download_dir(key_server).rglob("*.zip*"))


async def test_download_package_needs_a_key(server: EdiServer) -> None:
    await call_err(server, "edi_download_package", {"package": HBR}, "auth_required")


def test_sha1_fixture_matches_the_recorded_entity() -> None:
    """The recorded entity and PASTA's checksum fixture agree (guards re-recordings)."""
    root = Path(__file__).parent / "fixtures"
    manifest = json.loads((root / "manifest.json").read_text())
    by_key = {e["key"]: e for e in manifest}
    data = next(
        e for k, e in by_key.items() if k.endswith(f"/{THIESSEN}") and "package/data/eml" in k
    )
    checksum = next(e for k, e in by_key.items() if "data/checksum" in k and THIESSEN in k)
    body = (root / data["file"]).read_bytes()
    expected = (root / checksum["file"]).read_text().strip()
    assert hashlib.sha1(body, usedforsecurity=False).hexdigest() == expected


async def test_wide_preview_is_trimmed_to_the_budget(
    key_server: EdiServer, router: FixtureRouter
) -> None:
    header = ",".join(f"column_{i:02d}" for i in range(40))
    row = ",".join(f"{i * 1.234567:.6f}xyz" for i in range(40))
    body = (header + "\n" + "\n".join(row for _ in range(200)) + "\n").encode()
    router.add(PASTA_DATA, Reply(200, body, "text/csv"))
    p = await call_ok(
        key_server, "edi_preview_entity", {"package": HBR, "entity": THIESSEN, "rows": 200}
    )
    kept = len(p["rows"])
    assert 0 < kept < 200 and p["complete"] is False
    assert len(json.dumps(p, separators=(",", ":"), ensure_ascii=False)) <= 50_000 + 1000
    step = next(s for s in p["nextSteps"] if s.startswith("Result trimmed"))
    assert f"rows={kept}" in step and "offset" not in step
