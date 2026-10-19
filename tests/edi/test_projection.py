"""EML projection on a hand-written document covering what the recorded fixtures lack:
inline markup, ``references`` (including a cycle), EML 2.2 licensing and awards, taxonomy,
annotations, enumerated domains, size units and capped lists."""

# ruff: noqa: E501  (the inline EML keeps one element per line)

from __future__ import annotations

import json

from edi_mcp.edi.eml import entity_refs, pasta_entity_id
from edi_mcp.edi.xml import parse_xml, prose
from edi_mcp.projections import eml as proj
from edi_mcp.projections.eml import project_eml

GEO = "".join(
    f"<geographicCoverage><geographicDescription>Plot {i}</geographicDescription>"
    "<boundingCoordinates><westBoundingCoordinate>-107</westBoundingCoordinate>"
    "<eastBoundingCoordinate>-106.5</eastBoundingCoordinate>"
    "<northBoundingCoordinate>32.8</northBoundingCoordinate>"
    "<southBoundingCoordinate>32.4</southBoundingCoordinate></boundingCoordinates>"
    "</geographicCoverage>"
    for i in range(30)
)
CODES = "".join(
    f"<codeDefinition><code>C{i}</code><definition>Class {i}</definition></codeDefinition>"
    for i in range(60)
)

EML = f"""<?xml version="1.0" encoding="UTF-8"?>
<eml:eml xmlns:eml="https://eml.ecoinformatics.org/eml-2.2.0" packageId="edi.9.1" system="edi">
  <dataset>
    <alternateIdentifier>doi:10.6073/pasta/00000000000000000000000000000000</alternateIdentifier>
    <shortName>synthetic</shortName>
    <title>Synthetic   test
      package</title>
    <creator id="ada">
      <individualName><givenName>Ada</givenName><givenName>B.</givenName><surName>Lovelace</surName></individualName>
      <organizationName>Analytical Engines</organizationName>
      <electronicMailAddress>ada@example.org</electronicMailAddress>
      <userId directory="https://orcid.org">0000-0002-1825-0097</userId>
    </creator>
    <creator><references>ada</references></creator>
    <creator><references>loop-a</references></creator>
    <creator><positionName>Information Manager</positionName></creator>
    <associatedParty id="loop-a"><references>loop-b</references></associatedParty>
    <associatedParty id="loop-b"><references>loop-a</references></associatedParty>
    <pubDate>2026-01-02</pubDate>
    <language>english</language>
    <abstract>
      <section><title>Overview</title>
        <para>Rates of <emphasis>net</emphasis> primary production in g m<superscript>-2</superscript>
          per year; see <ulink url="https://example.org"><citetitle>the site</citetitle></ulink> for more.</para>
      </section>
      <para>Second paragraph.</para>
    </abstract>
    <keywordSet><keyword>npp</keyword><keyword>grassland</keyword>
      <keywordThesaurus>LTER Controlled Vocabulary</keywordThesaurus></keywordSet>
    <keywordSet><keyword>local</keyword></keywordSet>
    <intellectualRights><para>CC BY 4.0 with <emphasis>attribution</emphasis>.</para></intellectualRights>
    <licensed><licenseName>Creative Commons Attribution 4.0 International</licenseName>
      <url>https://spdx.org/licenses/CC-BY-4.0</url><identifier>CC-BY-4.0</identifier></licensed>
    <coverage>
      {GEO}
      <temporalCoverage><rangeOfDates>
        <beginDate><calendarDate>1990-01-01</calendarDate></beginDate>
        <endDate><calendarDate>2020-12-31</calendarDate></endDate></rangeOfDates></temporalCoverage>
      <temporalCoverage><singleDateTime><calendarDate>2001</calendarDate></singleDateTime></temporalCoverage>
      <taxonomicCoverage>
        <taxonomicClassification><taxonRankName>Kingdom</taxonRankName><taxonRankValue>Plantae</taxonRankValue>
          <taxonomicClassification><taxonRankName>Genus</taxonRankName><taxonRankValue>Bouteloua</taxonRankValue>
            <commonName>grama</commonName>
            <taxonomicClassification><taxonRankName>Species</taxonRankName><taxonRankValue>Bouteloua eriopoda</taxonRankValue></taxonomicClassification>
          </taxonomicClassification>
        </taxonomicClassification>
        <taxonomicClassification><taxonRankName>Kingdom</taxonRankName><taxonRankValue>Plantae</taxonRankValue></taxonomicClassification>
      </taxonomicCoverage>
    </coverage>
    <maintenance><description><para>Updated annually.</para></description></maintenance>
    <contact><references>ada</references></contact>
    <methods>
      <methodStep><description><para>Clip <emphasis>all</emphasis> biomass.</para></description></methodStep>
      <methodStep><description><para>Dry at 60 C.</para></description></methodStep>
      <sampling><studyExtent><description><para>Ten plots.</para></description></studyExtent>
        <samplingDescription><para>Stratified random.</para></samplingDescription></sampling>
    </methods>
    <project id="proj">
      <title>Synthetic project</title>
      <personnel><references>ada</references><role>Principal Investigator</role></personnel>
      <award><funderName>NSF</funderName><awardNumber>DEB-1</awardNumber><title>LTER</title>
        <awardUrl>https://nsf.gov/1</awardUrl></award>
      <funding><para>Private foundation</para></funding>
      <relatedProject><title>Parent project</title></relatedProject>
    </project>
    <dataTable id="t1">
      <entityName>npp table</entityName>
      <entityDescription>Annual NPP</entityDescription>
      <physical>
        <objectName>npp.csv</objectName>
        <size unit="byte">1234</size>
        <dataFormat><textFormat><numHeaderLines>1</numHeaderLines><recordDelimiter>\\n</recordDelimiter>
          <attributeOrientation>column</attributeOrientation>
          <simpleDelimited><fieldDelimiter>,</fieldDelimiter><quoteCharacter>"</quoteCharacter></simpleDelimited>
        </textFormat></dataFormat>
        <distribution><online><url function="download">https://pasta.lternet.edu/package/data/eml/edi/9/1/0123456789abcdef0123456789abcdef</url></online></distribution>
      </physical>
      <attributeList id="attrs">
        <attribute id="a-npp">
          <attributeName>npp</attributeName><attributeLabel>NPP</attributeLabel>
          <attributeDefinition>Net primary production</attributeDefinition><storageType>float</storageType>
          <measurementScale><ratio><unit><customUnit>gramsPerSquareMeterPerYear</customUnit></unit>
            <numericDomain><numberType>real</numberType><bounds><minimum exclusive="false">0</minimum><maximum exclusive="false">900.5</maximum></bounds></numericDomain>
          </ratio></measurementScale>
          <missingValueCode><code>NA</code><codeExplanation>not measured</codeExplanation></missingValueCode>
          <annotation><propertyURI label="has unit">http://qudt.org/schema/qudt/hasUnit</propertyURI>
            <valueURI label="gram per square metre">http://qudt.org/vocab/unit/GM-PER-M2</valueURI></annotation>
        </attribute>
        <attribute><attributeName>class</attributeName><attributeDefinition>Vegetation class</attributeDefinition>
          <measurementScale><nominal><nonNumericDomain><enumeratedDomain>{CODES}</enumeratedDomain></nonNumericDomain></nominal></measurementScale>
        </attribute>
        <attribute><attributeName>date</attributeName><attributeDefinition>Harvest date</attributeDefinition>
          <measurementScale><dateTime><formatString>YYYY-MM-DD</formatString></dateTime></measurementScale>
        </attribute>
        <attribute><attributeName>note</attributeName><attributeDefinition>Remarks</attributeDefinition>
          <measurementScale><nominal><nonNumericDomain><textDomain><definition>free text</definition></textDomain></nonNumericDomain></nominal></measurementScale>
        </attribute>
        <attribute><attributeName>temp</attributeName><attributeDefinition>Temperature</attributeDefinition>
          <measurementScale><interval><unit><standardUnit>celsius</standardUnit></unit>
            <numericDomain><numberType>real</numberType></numericDomain></interval></measurementScale>
        </attribute>
        <attribute><references>a-npp</references></attribute>
        <attribute><attributeDefinition>no name</attributeDefinition></attribute>
      </attributeList>
      <numberOfRecords>10</numberOfRecords>
    </dataTable>
    <otherEntity>
      <entityName>photos</entityName>
      <physical><objectName>photos.zip</objectName><size unit="kilobyte">20</size>
        <dataFormat><externallyDefinedFormat><formatName>application/zip</formatName></externallyDefinedFormat></dataFormat>
      </physical>
      <entityType>zip</entityType>
    </otherEntity>
  </dataset>
</eml:eml>"""


def _project(**kw: object) -> proj.EmlProjection:
    return project_eml(parse_xml(EML.encode(), source="test"), **kw)  # type: ignore[arg-type]


def test_overview_and_prose() -> None:
    p = _project()
    assert p.eml_version == "2.2.0" and p.title == "Synthetic test package"
    assert p.short_name == "synthetic" and p.language == "english"
    assert p.abstract == (
        "Overview\n\nRates of net primary production in g m-2 per year; see the site for "
        "more.\n\nSecond paragraph."
    )
    assert p.maintenance == "Updated annually."
    assert p.alternate_identifiers == ["doi:10.6073/pasta/00000000000000000000000000000000"]
    assert [k.model_dump(exclude_none=True) for k in p.keywords] == [
        {"thesaurus": "LTER Controlled Vocabulary", "keywords": ["npp", "grassland"]},
        {"keywords": ["local"]},
    ]
    assert p.keywords_total == 3


def test_text_is_cut_at_max_text_chars() -> None:
    p = _project(max_text_chars=50)
    assert p.abstract is not None and len(p.abstract) <= 50 and p.abstract.endswith("…")
    assert p.abstract_truncated
    short = _project(max_text_chars=20)
    assert short.abstract_truncated and short.methods is not None and short.methods.truncated


def test_people_resolve_references_and_survive_cycles() -> None:
    p = _project()
    ada = {
        "name": "Ada B. Lovelace",
        "organization": "Analytical Engines",
        "email": "ada@example.org",
        "orcid": "https://orcid.org/0000-0002-1825-0097",
    }
    # Second creator references the first; the third is a reference cycle and is skipped.
    assert [c.model_dump(exclude_none=True) for c in p.creators] == [
        ada,
        ada,
        {"name": "Information Manager", "position": "Information Manager"},
    ]
    assert p.creators_total == 3
    assert p.contacts[0].name == "Ada B. Lovelace"
    assert p.associated_parties == []
    assert p.project is not None
    assert p.project.personnel[0].role == "Principal Investigator"


def test_coverage_is_capped_with_totals() -> None:
    cov = _project().coverage
    assert cov.geographic_total == 30 and len(cov.geographic) == proj.MAX_GEOGRAPHIC
    assert cov.geographic[0].model_dump(exclude_none=True) == {
        "description": "Plot 0",
        "west": -107.0,
        "east": -106.5,
        "north": 32.8,
        "south": 32.4,
    }
    assert [t.model_dump(exclude_none=True) for t in cov.temporal] == [
        {"begin": "1990-01-01", "end": "2020-12-31"},
        {"date": "2001"},
    ]
    assert [(t.rank, t.name, t.common_names) for t in cov.taxa] == [
        ("Kingdom", "Plantae", None),
        ("Genus", "Bouteloua", ["grama"]),
        ("Species", "Bouteloua eriopoda", None),
    ]
    assert cov.taxa_total == 3


def test_methods_rights_project() -> None:
    p = _project()
    assert p.methods is not None and p.methods.steps == 2
    assert p.methods.text == (
        "Clip all biomass.\n\nDry at 60 C.\n\nSampling: Ten plots.\n\nSampling: Stratified random."
    )
    assert p.license is not None
    assert p.license.model_dump(exclude_none=True) == {
        "name": "Creative Commons Attribution 4.0 International",
        "url": "https://spdx.org/licenses/CC-BY-4.0",
        "identifier": "CC-BY-4.0",
        "text": "CC BY 4.0 with attribution.",
        "truncated": False,
    }
    assert p.project is not None and p.project.title == "Synthetic project"
    assert [f.model_dump(exclude_none=True) for f in p.project.funding] == [
        {"funder": "NSF", "award_number": "DEB-1", "title": "LTER", "url": "https://nsf.gov/1"},
        {"text": "Private foundation"},
    ]
    assert p.project.related_projects == ["Parent project"]


def test_entities_and_attributes() -> None:
    p = _project(entity_attributes=True)
    table, other = p.entities
    assert table.entity_id == "0123456789abcdef0123456789abcdef"  # from the PASTA URL
    assert other.entity_id == pasta_entity_id("photos")  # MD5 of the name otherwise
    assert (table.size, other.size) == (1234, None)  # a kilobyte size is not bytes
    assert other.format == "application/zip" and table.format == "text"
    assert table.number_of_records == 10 and table.attributes_total == 7
    assert table.text_format is not None
    assert table.text_format.model_dump(exclude_none=True) == {
        "header_lines": 1,
        "field_delimiter": ",",
        "record_delimiter": "\\n",
        "quote_character": '"',
        "orientation": "column",
    }
    npp, cls, date, note, temp, ref, *rest = table.attributes
    assert rest == []  # the attribute without a name is dropped
    assert npp.model_dump(exclude_none=True) == {
        "name": "npp",
        "label": "NPP",
        "definition": "Net primary production",
        "storage_type": "float",
        "scale": "ratio",
        "unit": "gramsPerSquareMeterPerYear",
        "number_type": "real",
        "minimum": 0.0,
        "maximum": 900.5,
        "missing_value_codes": [{"code": "NA", "definition": "not measured"}],
        "annotations": [
            {
                "property": "has unit",
                "property_uri": "http://qudt.org/schema/qudt/hasUnit",
                "value": "gram per square metre",
                "value_uri": "http://qudt.org/vocab/unit/GM-PER-M2",
            }
        ],
    }
    assert ref.name == "npp"  # <references> to another attribute
    assert cls.scale == "nominal" and cls.codes_total == 60
    assert cls.codes is not None and len(cls.codes) == proj.MAX_CODES
    assert cls.codes[0].model_dump() == {"code": "C0", "definition": "Class 0"}
    assert date.date_format == "YYYY-MM-DD" and date.scale == "dateTime"
    assert note.text_definition == "free text" and note.codes is None
    assert temp.scale == "interval" and temp.unit == "celsius" and temp.minimum is None


def test_entities_without_attributes_still_count_them() -> None:
    table = _project().entities[0]
    assert table.attributes == [] and table.attributes_total == 7


def test_entity_refs_accept_a_parsed_root_and_agree() -> None:
    root = parse_xml(EML.encode(), source="test")
    refs = entity_refs(root, source="test")
    assert [r.entity_id for r in refs] == [e.entity_id for e in project_eml(root).entities]
    assert refs[1].size is None  # kilobyte


def test_empty_and_minimal_documents() -> None:
    p = project_eml(parse_xml(b"<eml><dataset><title>t</title></dataset></eml>", source="x"))
    assert p.title == "t" and p.eml_version is None and p.entities == []
    assert p.methods is None and p.license is None and p.project is None
    none = project_eml(parse_xml(b"<eml/>", source="x"))
    assert none.title is None and none.coverage.geographic == []


def test_prose_falls_back_to_plain_text() -> None:
    root = parse_xml(b"<abstract>  plain\n text <b>bold</b> end </abstract>", source="x")
    assert prose(root) == "plain text bold end"
    assert prose(None) is None
    assert prose(parse_xml(b"<abstract/>", source="x")) is None


def test_projection_serializes_compactly() -> None:
    p = _project(entity_attributes=True)
    blob = json.dumps([e.model_dump(by_alias=True, exclude_none=True) for e in p.entities])
    assert '"missingValueCodes"' in blob and '"codes": []' not in blob
