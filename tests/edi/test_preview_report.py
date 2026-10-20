"""The preview parser and the quality-report projection, on hand-written input."""

from __future__ import annotations

import pytest

from edi_mcp.edi.preview import layout, parse_preview, unescape_delimiter
from edi_mcp.edi.xml import parse_xml
from edi_mcp.errors import ToolError
from edi_mcp.projections.report import MAX_ISSUES, project_report


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("\\t", "\t"),
        ("tab", "\t"),
        ("TAB", "\t"),
        ("#x09", "\t"),
        ("0x2C", ","),
        ("\\r\\n", "\r\n"),
        (",", ","),
        ("\t", "\t"),
        (" ", " "),
        ("", None),
        (None, None),
        ("comma", ","),
    ],
)
def test_unescape_delimiter(raw: str | None, expected: str | None) -> None:
    assert unescape_delimiter(raw) == expected


def test_layout_notes_assumptions() -> None:
    assert layout(None, None, 1).field_delimiter == ","
    assert layout(None, None, 1).notes == ["The EML names no field delimiter; assumed a comma."]
    multi = layout("::", None, None)
    assert multi.field_delimiter == "," and "not one character" in multi.notes[0]
    assert multi.header_lines is None
    assert layout("\\t", "'", 2).quote_character == "'"


def test_parse_tab_separated_with_quotes_and_header_lines() -> None:
    data = b'# comment line\nsite\tvalue\n"A\tB"\t1\nC\t2\nD\t3\nE\t4\nF\t'
    fmt = layout("\\t", '"', 2)
    p = parse_preview(data, eof=False, fmt=fmt, rows=3)
    assert p.header == ["site", "value"]
    assert p.rows == [["A\tB", "1"], ["C", "2"], ["D", "3"]] and p.complete is False
    # The cut last record ("F\t") is dropped when the stream stopped early.
    all_rows = parse_preview(data, eof=False, fmt=layout("\\t", '"', 2), rows=50)
    assert all_rows.rows[-1] == ["E", "4"] and all_rows.complete is False
    at_eof = parse_preview(data, eof=True, fmt=layout("\\t", '"', 2), rows=50)
    assert at_eof.rows[-1] == ["F", ""] and at_eof.complete is True


def test_header_detection_when_the_eml_is_silent() -> None:
    data = b"a,b\n1,2\n"
    by_names = parse_preview(
        data, eof=True, fmt=layout(",", None, None), rows=5, attribute_names=["A", "B"]
    )
    assert by_names.header == ["a", "b"] and by_names.rows == [["1", "2"]]
    not_names = parse_preview(
        b"1,2\n3,4\n", eof=True, fmt=layout(",", None, None), rows=5, attribute_names=["A", "B"]
    )
    assert not_names.header is None and len(not_names.rows) == 2
    sniffed = parse_preview(
        b"name,count\nx,1\ny,2\nz,3\n", eof=True, fmt=layout(",", None, None), rows=5
    )
    assert sniffed.header == ["name", "count"]


def test_binary_blank_lines_bom_and_wide_tables() -> None:
    with pytest.raises(ToolError) as err:
        parse_preview(b"\x89PNG\r\n\x00\x00", eof=True, fmt=layout(",", None, 0), rows=5)
    assert err.value.code == "invalid_argument"
    p = parse_preview("﻿h\n\n1\n".encode(), eof=True, fmt=layout(",", None, 1), rows=5)
    assert p.header == ["h"] and p.rows == [["1"]]
    wide = ",".join(str(i) for i in range(150)).encode() + b"\n"
    w = parse_preview(wide, eof=True, fmt=layout(",", None, 0), rows=5)
    assert len(w.rows[0]) == 100 and w.columns_cut == 50


REPORT = """<?xml version="1.0"?>
<qr:qualityReport xmlns="eml://ecoinformatics.org/qualityReport"
    xmlns:qr="eml://ecoinformatics.org/qualityReport">
  <creationDate>2026-10-16T19:45:45</creationDate>
  <packageId>x.1.1</packageId>
  <datasetReport>
    <qualityCheck><identifier>a</identifier><status>valid</status></qualityCheck>
    <qualityCheck><identifier>b</identifier><name>B</name><status>warn</status>
      <found>{long}</found><explanation>why</explanation><suggestion>fix</suggestion></qualityCheck>
    <qualityCheck><identifier>c</identifier><status>info</status></qualityCheck>
    <qualityCheck><identifier>d</identifier><status>bogus</status></qualityCheck>
  </datasetReport>
  <entityReport>
    <entityName>table</entityName>
    <qualityCheck><identifier>e</identifier><status>error</status></qualityCheck>
    <qualityCheck><identifier>f</identifier><status>valid</status></qualityCheck>
  </entityReport>
</qr:qualityReport>"""


def test_project_report() -> None:
    root = parse_xml(REPORT.format(long="x" * 500), source="test")
    r = project_report(root)
    assert r.package_id == "x.1.1" and r.created == "2026-10-16T19:45:45"
    assert r.counts.model_dump() == {"valid": 2, "info": 1, "warn": 1, "error": 1}
    assert [i.identifier for i in r.issues] == ["e", "b"]  # errors first
    assert r.issues[0].entity == "table" and r.issues[1].entity is None
    assert r.issues[1].found is not None and len(r.issues[1].found) == 200
    assert r.entities[0].counts.model_dump() == {"valid": 1, "info": 0, "warn": 0, "error": 1}
    with_info = project_report(root, include_info=True)
    assert with_info.issues_total == 3 and with_info.issues[-1].identifier == "c"


def test_project_report_caps_issues() -> None:
    checks = "".join(
        f"<qualityCheck><identifier>w{i}</identifier><status>warn</status></qualityCheck>"
        for i in range(MAX_ISSUES + 7)
    )
    root = parse_xml(
        f"<qualityReport><datasetReport>{checks}</datasetReport></qualityReport>", source="t"
    )
    r = project_report(root)
    assert len(r.issues) == MAX_ISSUES and r.issues_total == MAX_ISSUES + 7
