"""The scope snapshot and tolerant scope resolution (DESIGN.md D9)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from edi_mcp.edi.scopes import (
    SCOPE_CODE_RE,
    load_scopes,
    name_score,
    resolve_reference,
    resolve_scope,
)
from edi_mcp.errors import ToolError


def test_snapshot_is_consistent() -> None:
    snapshot = load_scopes()
    scopes = [r.scope for r in snapshot.records]
    assert len(scopes) == len(set(scopes)) == 41 and scopes == sorted(scopes)
    assert all(SCOPE_CODE_RE.match(s) for s in scopes)
    names = [r.name for r in snapshot.records if r.name]
    assert len(names) == len(set(names))
    codes = [r.site_code for r in snapshot.records if r.site_code]
    assert len(codes) == len(set(codes)) == 31
    for record in snapshot.records:
        if record.site_code:
            assert record.scope == f"knb-lter-{record.site_code.lower()}"
            assert record.kind == "lter" and record.name and record.location
        assert record.pasta_packages > 0
    assert {r.scope for r in snapshot.records if r.kind == "bulk"} == {
        "ecotrends",
        "lter-landsat",
        "lter-landsat-ledaps",
    }
    unreplicated = {r.scope for r in snapshot.records if not r.dataone_replicated}
    assert unreplicated == {"cos-spu", "icarus"}


def test_every_name_and_site_code_resolves_to_its_scope() -> None:
    for record in load_scopes().records:
        if record.site_code:
            assert resolve_scope(record.site_code.lower())[0] == record.scope
        if record.name:
            assert resolve_scope(record.name)[0] == record.scope, record.name


@pytest.mark.parametrize(
    ("value", "scope", "echoed"),
    [
        ("knb-lter-jrn", "knb-lter-jrn", False),
        ("KNB-LTER-JRN", "knb-lter-jrn", False),
        ("edi", "edi", False),
        ("jrn", "knb-lter-jrn", True),
        ("JRN", "knb-lter-jrn", True),
        ("Jornada", "knb-lter-jrn", True),
        ("jornad", "knb-lter-jrn", True),
        ("Hubbard Brook", "knb-lter-hbr", True),
        ("Toolik", "knb-lter-arc", True),
        ("arctic", "knb-lter-arc", True),
        ("Kansas", "knb-lter-knz", True),
        ("Palmer", "knb-lter-pal", True),
        ("PalEON", "msb-paleon", True),
        ("pal", "knb-lter-pal", True),
        # Three-letter codes always mean the LTER site; msb-cap needs its exact code.
        ("cap", "knb-lter-cap", True),
        ("msb-cap", "msb-cap", False),
        ("Seattle", "cos-spu", True),
    ],
)
def test_resolves(value: str, scope: str, echoed: bool) -> None:
    got, resolved = resolve_scope(value)
    assert got == scope
    assert (resolved is not None) is echoed
    if resolved is not None:
        assert resolved.input == value and resolved.code == scope
        assert resolved.confidence >= 0.75


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Alaska", {"knb-lter-arc", "knb-lter-ble", "knb-lter-bnz", "knb-lter-nga"}),
        ("Antarctica", {"knb-lter-mcm", "knb-lter-pal"}),
        ("California", {"knb-lter-cce", "knb-lter-sbc"}),
        ("New Mexico", {"knb-lter-jrn", "knb-lter-sev"}),
        ("Landsat", {"lter-landsat", "lter-landsat-ledaps"}),
        ("LTER", {"knb-lter-nwk", "knb-lter-and"}),
    ],
)
def test_shared_names_and_locations_are_ambiguous(value: str, expected: set[str]) -> None:
    with pytest.raises(ToolError) as exc:
        resolve_scope(value)
    assert exc.value.code == "ambiguous_input"
    assert expected <= {c["scope"] for c in exc.value.details["candidates"]}


def test_unknown_names_and_new_codes() -> None:
    # Hyphenated or one-word codes the snapshot lacks pass through: the backend decides.
    assert resolve_scope("knb-lter-new") == ("knb-lter-new", None)
    assert resolve_scope("xyz") == ("xyz", None)
    with pytest.raises(ToolError) as exc:
        resolve_scope("Foo Bar Baz")
    assert exc.value.code == "not_found" and "edi_list_scopes" in (exc.value.hint or "")


def test_name_score() -> None:
    assert name_score("Jornada Basin LTER", "Jornada Basin LTER") == 1.0
    assert name_score("Jornada", "Jornada Basin LTER") == 0.95
    assert name_score("Basin", "Jornada Basin LTER") == 0.9
    assert name_score("Basin Jornada", "Jornada Basin LTER") == 0.85
    assert name_score("", "x") == 0.0
    assert name_score("Blue Ridge", "Blue River") < 0.75


@pytest.mark.parametrize(
    ("value", "package", "revision", "echoed"),
    [
        ("knb-lter-hbr.14", "knb-lter-hbr.14", None, []),
        ("jrn.210548103", "knb-lter-jrn.210548103", None, ["knb-lter-jrn"]),
        ("JRN/210548103/43", "knb-lter-jrn.210548103.43", 43, ["knb-lter-jrn"]),
        ("Jornada Basin.210548103.43", "knb-lter-jrn.210548103.43", 43, ["knb-lter-jrn"]),
        ("hubbard brook/14/newest", "knb-lter-hbr.14", "newest", ["knb-lter-hbr"]),
        ("knb-lter-new.3", "knb-lter-new.3", None, []),
    ],
)
def test_resolve_reference(value: str, package: str, revision: object, echoed: list[str]) -> None:
    ref, resolved = resolve_reference(value)
    assert str(ref.package) == package and ref.revision == revision
    assert [r.code for r in resolved] == echoed
    assert ref.raw == value


def test_resolve_reference_keeps_dois_and_errors() -> None:
    ref, resolved = resolve_reference("doi:10.6073/pasta/2017345f0977c0f7c46e1ad90ce1b062")
    assert ref.doi is not None and resolved == []
    with pytest.raises(ToolError) as exc:
        resolve_reference("not a package")
    assert exc.value.code == "invalid_argument"
    with pytest.raises(ToolError) as exc:
        resolve_reference("Alaska.12")
    assert exc.value.code == "ambiguous_input"


@given(st.text(max_size=60))
def test_resolve_scope_only_raises_tool_errors(value: str) -> None:
    try:
        scope, _ = resolve_scope(value)
    except ToolError as err:
        assert err.code in ("not_found", "ambiguous_input")
    else:
        assert scope
