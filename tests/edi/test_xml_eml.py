"""Hardened XML parsing and EML entity references (DESIGN.md D8)."""

from __future__ import annotations

import pytest

from edi_mcp.edi.eml import entity_refs, pasta_entity_id
from edi_mcp.edi.xml import parse_xml, text_of
from edi_mcp.errors import EdiApiError
from tests.fixture_router import FIXTURES, load_manifest

BOMB = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;">]>
<eml>&lol2;</eml>"""
EXTERNAL = b"""<?xml version="1.0"?>
<!DOCTYPE x [<!ENTITY ext SYSTEM "file:///etc/passwd">]><eml>&ext;</eml>"""


@pytest.mark.parametrize("payload", [BOMB, EXTERNAL, b"<unclosed>", b"not xml at all"])
def test_dangerous_or_broken_xml_is_a_decode_error(payload: bytes) -> None:
    with pytest.raises(EdiApiError) as exc:
        parse_xml(payload, source="/package/metadata/eml/x")
    assert exc.value.kind == "decode"


def test_text_of_follows_local_names() -> None:
    root = parse_xml(b'<a xmlns="urn:x"><b><c>  two\n words </c></b><e/></a>', source="t")
    assert text_of(root, "b", "c") == "two words"
    assert text_of(root, "missing", "c") is None
    assert text_of(root, "e") is None


def _hbr_eml() -> bytes:
    entry = load_manifest()["GET pasta.lternet.edu/package/metadata/eml/knb-lter-hbr/14/22"]
    return (FIXTURES / entry["file"]).read_bytes()


def test_entity_refs_from_recorded_eml() -> None:
    refs = entity_refs(_hbr_eml(), source="hbr")
    names = [r.name for r in refs]
    assert "Daily Watershed Precipitation" in names and len(refs) == 5
    thiessen = next(r for r in refs if r.name == "thiessen_weights")
    assert thiessen.entity_id == "c4f72fa0cb155f1b61f1333bb67e3d00"
    assert thiessen.url and thiessen.url.endswith(thiessen.entity_id)
    # Entities without a PASTA URL still get PASTA's id: the MD5 of the entity name.
    for ref in refs:
        assert ref.entity_id == pasta_entity_id(ref.name or "")


def test_entity_refs_shapes() -> None:
    eml = b"""<eml:eml xmlns:eml="https://eml.ecoinformatics.org/eml-2.2.0"><dataset>
      <title>t</title>
      <dataTable><entityName>Table A</entityName><physical><objectName>a.csv</objectName>
        <size unit="byte">12.0</size><dataFormat><textFormat/></dataFormat>
        <distribution><online><url>https://example.org/a.csv</url></online></distribution>
      </physical></dataTable>
      <otherEntity><entityName>Zip</entityName><physical><size>big</size><dataFormat>
        <externallyDefinedFormat><formatName>application/zip</formatName></externallyDefinedFormat>
      </dataFormat></physical></otherEntity>
      <spatialRaster><entityName>Raster</entityName></spatialRaster>
    </dataset></eml:eml>"""
    a, z, r = entity_refs(eml, source="t")
    assert (a.entity_type, a.object_name, a.size, a.format) == ("dataTable", "a.csv", 12, "text")
    assert a.entity_id == pasta_entity_id("Table A") and a.url == "https://example.org/a.csv"
    assert (z.format, z.size) == ("application/zip", None)
    assert (r.entity_type, r.url, r.size) == ("spatialRaster", None, None)
    assert entity_refs(b"<eml/>", source="t") == []
