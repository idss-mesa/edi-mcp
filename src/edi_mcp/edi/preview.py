"""Parse the first rows of a delimited data entity (``edi_preview_entity``).

The bytes come from a stream the caller stopped reading early (GMN ignores
``Range``), so the last record may be cut: it is dropped unless the stream
reached its end. The EML ``physical/dataFormat/textFormat`` gives the layout;
its delimiters are often written as escape text (``\\t``, ``\\r\\n``) or words
(``tab``) and are unescaped here (RESEARCH.md section 6).
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from edi_mcp.errors import ToolError

#: Cells longer than this are cut (with an ellipsis) so wide text columns stay small.
MAX_CELL_CHARS = 200
MAX_COLUMNS = 100
_WORDS = {
    "tab": "\t",
    "comma": ",",
    "semicolon": ";",
    "space": " ",
    "pipe": "|",
    "colon": ":",
}
_ESCAPES = {"\\t": "\t", "\\n": "\n", "\\r": "\r", "\\\\": "\\"}
_HEX_RE = re.compile(r"^(?:#x|0x|\\x|\\u|u\+)([0-9a-fA-F]{2,4});?$")


def unescape_delimiter(value: str | None) -> str | None:
    """``\\t`` / ``tab`` / ``#x09`` / ``0x09`` → a real tab; ``\\r\\n`` → CR LF."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        # A literal space or tab survives as itself.
        return value if value in (" ", "\t") else None
    word = _WORDS.get(text.lower())
    if word is not None:
        return word
    m = _HEX_RE.match(text)
    if m:
        return chr(int(m.group(1), 16))
    return re.sub(r"\\[tnr\\]", lambda mm: _ESCAPES[mm.group(0)], text)


@dataclass
class Layout:
    field_delimiter: str = ","
    quote_character: str | None = '"'
    #: None when the EML does not say: the header is then detected (see parse_preview).
    header_lines: int | None = 0
    notes: list[str] = field(default_factory=list)


def layout(
    field_delimiter: str | None, quote_character: str | None, header_lines: int | None
) -> Layout:
    """The parsing layout from EML values (None when the EML is silent)."""
    out = Layout(header_lines=max(header_lines, 0) if header_lines is not None else None)
    delimiter = unescape_delimiter(field_delimiter)
    if delimiter is None:
        out.notes.append("The EML names no field delimiter; assumed a comma.")
    elif len(delimiter) != 1:
        out.notes.append(
            f"The EML field delimiter {field_delimiter!r} is not one character; assumed a comma."
        )
    else:
        out.field_delimiter = delimiter
    quote = unescape_delimiter(quote_character)
    if quote is not None and len(quote) == 1:
        out.quote_character = quote
    return out


@dataclass
class Preview:
    header: list[str] | None
    rows: list[list[str]]
    complete: bool
    cells_cut: int = 0
    columns_cut: int = 0


def looks_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def _cell(value: str, counter: list[int]) -> str:
    if len(value) > MAX_CELL_CHARS:
        counter[0] += 1
        return value[: MAX_CELL_CHARS - 1] + "…"
    return value


def _detect_header(first: list[str], text: str, attribute_names: list[str]) -> bool:
    """Whether the first record is a header when the EML gives no header-line count:
    it names at least half of the EML attributes, or csv.Sniffer thinks so."""
    cells = {c.strip().lower() for c in first if c.strip()}
    names = {n.strip().lower() for n in attribute_names if n and n.strip()}
    if names and cells:
        return len(cells & names) * 2 >= min(len(cells), len(names))
    try:
        return csv.Sniffer().has_header(text[:16384])
    except csv.Error:
        return False


def parse_preview(
    data: bytes,
    *,
    eof: bool,
    fmt: Layout,
    rows: int,
    attribute_names: list[str] | None = None,
) -> Preview:
    """Header (the last header line) and up to ``rows`` records of ``data``."""
    if looks_binary(data):
        raise ToolError(
            "invalid_argument",
            "This entity is binary, not delimited text, so it cannot be previewed.",
            hint="Download it with edi_download_entities instead.",
        )
    text = data.decode("utf-8", "replace").lstrip("﻿")
    if not eof:
        # The stream stopped mid-record: drop everything after the last line break.
        cut = max(text.rfind("\n"), text.rfind("\r"))
        text = text[: cut + 1] if cut >= 0 else ""
    reader = csv.reader(
        io.StringIO(text, newline=""),
        delimiter=fmt.field_delimiter,
        quotechar=fmt.quote_character or '"',
        quoting=csv.QUOTE_MINIMAL if fmt.quote_character else csv.QUOTE_NONE,
        strict=False,
    )
    header: list[str] | None = None
    out: list[list[str]] = []
    cut_cells = [0]
    columns_cut = 0
    complete = eof
    header_lines = fmt.header_lines
    try:
        for index, record in enumerate(reader):
            if header_lines is None:
                header_lines = 1 if _detect_header(record, text, attribute_names or []) else 0
                fmt.notes.append(
                    "The EML gives no header-line count; the first line was "
                    + ("taken as the header." if header_lines else "taken as data.")
                )
            if index < header_lines:
                header = record
                continue
            if not record or all(not c.strip() for c in record):
                continue
            if len(out) >= rows:
                complete = False
                break
            if len(record) > MAX_COLUMNS:
                columns_cut = max(columns_cut, len(record) - MAX_COLUMNS)
                record = record[:MAX_COLUMNS]
            out.append([_cell(c, cut_cells) for c in record])
    except csv.Error as exc:
        raise ToolError(
            "invalid_argument",
            f"The entity could not be parsed as delimited text ({exc}).",
            hint="Download it with edi_download_entities instead.",
        ) from None
    if header is not None:
        header = [_cell(h.strip(), cut_cells) for h in header[:MAX_COLUMNS]]
    return Preview(header, out, complete, cut_cells[0], columns_cut)


__all__ = [
    "MAX_CELL_CHARS",
    "MAX_COLUMNS",
    "Layout",
    "Preview",
    "layout",
    "looks_binary",
    "parse_preview",
    "unescape_delimiter",
]
