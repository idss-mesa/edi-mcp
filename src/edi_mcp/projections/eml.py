"""EML → compact metadata models (``edi_get_metadata``, ``edi_list_entities``).

The EML is parsed once (defusedxml, :mod:`edi_mcp.edi.xml`) and projected
here. Every list is capped at projection time with a ``…Total`` count beside
it, because one EML can hold thousands of coverages, taxa or attributes
(``knb-lter-mcr.6`` is 3.4 MB) and the registry's budget trims only one list.
Prose (abstract, methods, rights) is read with :func:`prose` so inline markup
survives, then cut to ``max_text_chars``. ``<references>`` (EML's re-use of an
element by ``id``) is resolved through one id map with a cycle guard.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Literal
from xml.etree.ElementTree import Element

from pydantic import Field

from edi_mcp.edi.eml import ENTITY_TYPES, pasta_entity_id, size_bytes
from edi_mcp.edi.xml import child, children, descendants, local, prose, squash, text_of
from edi_mcp.models.common import EdiOutput

MAX_PEOPLE = 25
MAX_KEYWORDS = 60
MAX_GEOGRAPHIC = 25
MAX_TEMPORAL = 25
MAX_TAXA = 50
MAX_ENTITIES = 200
MAX_ATTRIBUTES = 250
MAX_CODES = 50
MAX_MISSING = 10
MAX_ANNOTATIONS = 10
MAX_FUNDING = 10
MAX_RELATED = 10
MAX_IDS = 10
MAX_REFERENCE_DEPTH = 8
_ORCID_RE = re.compile(r"(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", re.IGNORECASE)
_PASTA_ENTITY_RE = re.compile(r"/package/data/eml/[^/]+/\d+/\d+/(?P<entity>[0-9a-f]{32})$")

Scale = Literal["nominal", "ordinal", "interval", "ratio", "dateTime"]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Person(EdiOutput):
    name: str | None = Field(None, description="Person, else position, else organization.")
    organization: str | None = None
    position: str | None = None
    email: str | None = None
    orcid: str | None = Field(None, description="https://orcid.org/… when the EML gives one.")
    role: str | None = None


class KeywordSet(EdiOutput):
    thesaurus: str | None = None
    keywords: list[str]


class GeographicCoverage(EdiOutput):
    description: str | None = None
    west: float | None = None
    east: float | None = None
    north: float | None = None
    south: float | None = None


class TemporalCoverage(EdiOutput):
    begin: str | None = Field(None, description="Start of a date range.")
    end: str | None = Field(None, description="End of a date range.")
    date: str | None = Field(None, description="A single date.")


class Taxon(EdiOutput):
    rank: str | None = None
    name: str
    common_names: list[str] | None = None


class Coverage(EdiOutput):
    geographic: list[GeographicCoverage] = Field(default_factory=list)
    geographic_total: int = 0
    temporal: list[TemporalCoverage] = Field(default_factory=list)
    temporal_total: int = 0
    taxa: list[Taxon] = Field(default_factory=list)
    taxa_total: int = 0


class Methods(EdiOutput):
    text: str | None = Field(None, description="Method steps, sampling and quality control.")
    steps: int = Field(0, description="Number of methodStep elements.")
    truncated: bool = False


class License(EdiOutput):
    name: str | None = Field(None, description="EML 2.2 licensed/licenseName.")
    url: str | None = None
    identifier: str | None = Field(None, description="SPDX identifier when given.")
    text: str | None = Field(None, description="intellectualRights text.")
    truncated: bool = False


class Funding(EdiOutput):
    funder: str | None = None
    award_number: str | None = None
    title: str | None = None
    url: str | None = None
    text: str | None = Field(None, description="EML 2.1 free-text funding.")


class Project(EdiOutput):
    title: str | None = None
    personnel: list[Person] = Field(default_factory=list)
    funding: list[Funding] = Field(default_factory=list)
    related_projects: list[str] = Field(default_factory=list)


class Code(EdiOutput):
    code: str
    definition: str | None = None


class Annotation(EdiOutput):
    property: str | None = Field(None, description="Property label.")
    property_uri: str | None = None
    value: str | None = Field(None, description="Value label.")
    value_uri: str | None = None


class Attribute(EdiOutput):
    name: str
    label: str | None = None
    definition: str | None = None
    storage_type: str | None = None
    scale: Scale | None = Field(None, description="EML measurementScale.")
    unit: str | None = Field(None, description="standardUnit or customUnit.")
    number_type: str | None = Field(None, description="natural, whole, integer or real.")
    minimum: float | None = None
    maximum: float | None = None
    date_format: str | None = Field(None, description="dateTime formatString, e.g. YYYY-MM-DD.")
    text_definition: str | None = Field(None, description="textDomain definition.")
    codes: list[Code] | None = Field(None, description="enumeratedDomain codes.")
    codes_total: int | None = None
    missing_value_codes: list[Code] | None = None
    annotations: list[Annotation] | None = None


class TextFormat(EdiOutput):
    header_lines: int | None = None
    footer_lines: int | None = None
    field_delimiter: str | None = None
    record_delimiter: str | None = None
    quote_character: str | None = None
    orientation: str | None = Field(None, description="column or row (attributeOrientation).")


class EntityMetadata(EdiOutput):
    entity_id: str | None = Field(None, description="PASTA entity id (MD5 of the name).")
    name: str | None = None
    entity_type: str = Field(description="dataTable, otherEntity, spatialRaster, …")
    description: str | None = None
    object_name: str | None = Field(None, description="File name.")
    format: str | None = None
    size: int | None = Field(None, description="Bytes per the EML (only when its unit is bytes).")
    number_of_records: int | None = None
    text_format: TextFormat | None = None
    url: str | None = Field(None, description="Distribution URL in the EML.")
    attributes: list[Attribute] = Field(default_factory=list)
    attributes_total: int = 0


@dataclass
class EmlProjection:
    eml_version: str | None
    title: str | None
    short_name: str | None
    abstract: str | None
    abstract_truncated: bool
    keywords: list[KeywordSet]
    keywords_total: int
    pub_date: str | None
    language: str | None
    alternate_identifiers: list[str]
    maintenance: str | None
    creators: list[Person]
    creators_total: int
    contacts: list[Person]
    associated_parties: list[Person]
    publisher: Person | None
    coverage: Coverage
    methods: Methods | None
    license: License | None
    project: Project | None
    entities: list[EntityMetadata]
    entities_total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Refs:
    """Resolve ``<references>`` through one id map; a cycle or a dangling id is ``None``."""

    def __init__(self, root: Element) -> None:
        self.ids: dict[str, Element] = {}
        for element in root.iter():
            ident = element.get("id")
            if ident and ident not in self.ids:
                self.ids[ident] = element

    def __call__(self, element: Element | None) -> Element | None:
        seen: set[str] = set()
        current = element
        for _ in range(MAX_REFERENCE_DEPTH):
            if current is None:
                return None
            ref = child(current, "references")
            if ref is None or not (ref.text or "").strip():
                return current
            target = (ref.text or "").strip()
            if target in seen:
                return None
            seen.add(target)
            current = self.ids.get(target)
        return None

    def each(self, elements: Iterable[Element]) -> Iterator[Element]:
        for element in elements:
            resolved = self(element)
            if resolved is not None:
                yield resolved


def cut(text: str | None, limit: int) -> tuple[str | None, bool]:
    if text is None or len(text) <= limit:
        return text, False
    return text[: max(limit - 1, 0)].rstrip() + "…", True


def _float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int(text: str | None) -> int | None:
    value = _float(text)
    return int(value) if value is not None else None


def _orcid(party: Element) -> str | None:
    for uid in children(party, "userId"):
        directory = (uid.get("directory") or "").lower()
        text = squash(uid.text or "")
        m = _ORCID_RE.search(text)
        if m and ("orcid" in directory or "orcid" in text.lower() or text == m.group(1)):
            return f"https://orcid.org/{m.group(1).upper()}"
    return None


def person(party: Element, role: str | None = None) -> Person:
    individual = child(party, "individualName")
    name = None
    if individual is not None:
        given = " ".join(squash(g.text) for g in children(individual, "givenName") if g.text)
        sur = text_of(individual, "surName")
        name = squash(f"{given} {sur or ''}") or None
    organization = text_of(party, "organizationName")
    position = text_of(party, "positionName")
    email = next((squash(e.text) for e in children(party, "electronicMailAddress") if e.text), None)
    return Person(
        name=name or position or organization,
        organization=organization,
        position=position,
        email=email,
        orcid=_orcid(party),
        role=role or text_of(party, "role"),
    )


def _people(refs: _Refs, elements: Iterable[Element], role: str | None = None) -> list[Person]:
    """Parties, resolving ``<references>``; a role written beside the reference wins
    (``<personnel><references>x</references><role>PI</role></personnel>``)."""
    out = []
    for element in elements:
        party = refs(element)
        if party is not None:
            out.append(person(party, text_of(element, "role") or role))
    return out


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _keywords(dataset: Element) -> tuple[list[KeywordSet], int]:
    sets: list[KeywordSet] = []
    total = 0
    budget = MAX_KEYWORDS
    for group in children(dataset, "keywordSet"):
        words = [squash(k.text) for k in children(group, "keyword") if k.text and k.text.strip()]
        total += len(words)
        if budget <= 0 or not words:
            continue
        sets.append(
            KeywordSet(thesaurus=text_of(group, "keywordThesaurus"), keywords=words[:budget])
        )
        budget -= len(words[:budget])
    return sets, total


def _taxa(node: Element, out: list[Taxon], seen: set[tuple[str | None, str]]) -> int:
    count = 0
    for classification in children(node, "taxonomicClassification"):
        value = text_of(classification, "taxonRankValue")
        if value:
            rank = text_of(classification, "taxonRankName")
            key = (rank, value)
            if key not in seen:
                seen.add(key)
                count += 1
                if len(out) < MAX_TAXA:
                    common = [
                        squash(c.text) for c in children(classification, "commonName") if c.text
                    ]
                    out.append(Taxon(rank=rank, name=value, common_names=common or None))
        count += _taxa(classification, out, seen)
    return count


def coverage(refs: _Refs, node: Element | None) -> Coverage:
    cov = refs(node)
    result = Coverage()
    if cov is None:
        return result
    geo = list(refs.each(children(cov, "geographicCoverage")))
    result.geographic_total = len(geo)
    for g in geo[:MAX_GEOGRAPHIC]:
        box = child(g, "boundingCoordinates")
        result.geographic.append(
            GeographicCoverage(
                description=text_of(g, "geographicDescription"),
                west=_float(text_of(box, "westBoundingCoordinate")),
                east=_float(text_of(box, "eastBoundingCoordinate")),
                north=_float(text_of(box, "northBoundingCoordinate")),
                south=_float(text_of(box, "southBoundingCoordinate")),
            )
        )
    temporal: list[TemporalCoverage] = []
    for t in refs.each(children(cov, "temporalCoverage")):
        for r in children(t, "rangeOfDates"):
            temporal.append(
                TemporalCoverage(
                    begin=text_of(r, "beginDate", "calendarDate"),
                    end=text_of(r, "endDate", "calendarDate"),
                )
            )
        for d in children(t, "singleDateTime"):
            temporal.append(TemporalCoverage(date=text_of(d, "calendarDate")))
    result.temporal_total = len(temporal)
    result.temporal = temporal[:MAX_TEMPORAL]
    taxa: list[Taxon] = []
    seen: set[tuple[str | None, str]] = set()
    total = 0
    for t in refs.each(children(cov, "taxonomicCoverage")):
        total += _taxa(t, taxa, seen)
    result.taxa, result.taxa_total = taxa, total
    return result


def methods(refs: _Refs, node: Element | None, limit: int) -> Methods | None:
    m = refs(node)
    if m is None:
        return None
    parts: list[str] = []
    steps = list(children(m, "methodStep"))
    for step in steps:
        text = prose(child(step, "description"))
        if text:
            parts.append(text)
    sampling = child(m, "sampling")
    if sampling is not None:
        for name in ("studyExtent", "samplingDescription"):
            text = prose(child(sampling, name))
            if text:
                parts.append(f"Sampling: {text}")
    for qc in children(m, "qualityControl"):
        text = prose(child(qc, "description"))
        if text:
            parts.append(f"Quality control: {text}")
    text, truncated = cut("\n\n".join(parts) or None, limit)
    return Methods(text=text, steps=len(steps), truncated=truncated)


def license_of(dataset: Element, limit: int) -> License | None:
    licensed = child(dataset, "licensed")
    text, truncated = cut(prose(child(dataset, "intellectualRights")), limit)
    if licensed is None and text is None:
        return None
    return License(
        name=text_of(licensed, "licenseName"),
        url=text_of(licensed, "url"),
        identifier=text_of(licensed, "identifier"),
        text=text,
        truncated=truncated,
    )


def project(refs: _Refs, node: Element | None) -> Project | None:
    p = refs(node)
    if p is None:
        return None
    funding: list[Funding] = []
    for award in children(p, "award"):
        funding.append(
            Funding(
                funder=text_of(award, "funderName"),
                award_number=text_of(award, "awardNumber"),
                title=text_of(award, "title"),
                url=text_of(award, "awardUrl"),
            )
        )
    for f in children(p, "funding"):
        text = prose(f)
        if text:
            funding.append(Funding(text=text))
    related = [
        title for r in refs.each(children(p, "relatedProject")) if (title := text_of(r, "title"))
    ]
    return Project(
        title=text_of(p, "title"),
        personnel=_people(refs, children(p, "personnel"))[:MAX_PEOPLE],
        funding=funding[:MAX_FUNDING],
        related_projects=related[:MAX_RELATED],
    )


# ---------------------------------------------------------------------------
# Entities and attributes
# ---------------------------------------------------------------------------


def _codes(domain: Element) -> tuple[list[Code], int]:
    codes = [
        Code(code=c, definition=text_of(cd, "definition"))
        for cd in descendants(domain, "codeDefinition")
        if (c := text_of(cd, "code"))
    ]
    return codes[:MAX_CODES], len(codes)


def _annotations(element: Element) -> list[Annotation]:
    out = []
    for a in children(element, "annotation"):
        prop, value = child(a, "propertyURI"), child(a, "valueURI")
        out.append(
            Annotation(
                property=prop.get("label") if prop is not None else None,
                property_uri=text_of(a, "propertyURI"),
                value=value.get("label") if value is not None else None,
                value_uri=text_of(a, "valueURI"),
            )
        )
    return out[:MAX_ANNOTATIONS]


def attribute(refs: _Refs, element: Element) -> Attribute | None:
    a = refs(element)
    name = text_of(a, "attributeName") if a is not None else None
    if a is None or not name:
        return None
    out = Attribute(
        name=name,
        label=text_of(a, "attributeLabel"),
        definition=text_of(a, "attributeDefinition"),
        storage_type=text_of(a, "storageType"),
        missing_value_codes=[
            Code(code=c, definition=text_of(m, "codeExplanation"))
            for m in children(a, "missingValueCode")
            if (c := text_of(m, "code"))
        ][:MAX_MISSING]
        or None,
        annotations=_annotations(a) or None,
    )
    scale_el = child(a, "measurementScale")
    scale = next(iter(scale_el), None) if scale_el is not None else None
    if scale is None:
        return out
    kind = local(scale.tag)
    if kind in ("nominal", "ordinal", "interval", "ratio", "dateTime"):
        out.scale = kind  # type: ignore[assignment]
    if kind in ("interval", "ratio"):
        unit = child(scale, "unit")
        if unit is not None:
            out.unit = text_of(unit, "standardUnit") or text_of(unit, "customUnit")
        out.number_type = text_of(scale, "numericDomain", "numberType")
        domain_el = child(scale, "numericDomain")
        bounds = child(domain_el if domain_el is not None else scale, "bounds")
        if bounds is not None:
            out.minimum = _float(text_of(bounds, "minimum"))
            out.maximum = _float(text_of(bounds, "maximum"))
    elif kind == "dateTime":
        out.date_format = text_of(scale, "formatString")
    else:
        domain = child(scale, "nonNumericDomain")
        if domain is not None:
            enumerated = child(domain, "enumeratedDomain")
            if enumerated is not None:
                codes, total = _codes(enumerated)
                out.codes, out.codes_total = codes or None, total
            out.text_definition = text_of(domain, "textDomain", "definition")
    return out


def _text_format(physical: Element | None) -> TextFormat | None:
    fmt = child(child(physical, "dataFormat"), "textFormat")
    if fmt is None:
        return None
    simple = child(child(fmt, "simpleDelimited"), "fieldDelimiter")
    return TextFormat(
        header_lines=_int(text_of(fmt, "numHeaderLines")),
        footer_lines=_int(text_of(fmt, "numFooterLines")),
        field_delimiter=simple.text if simple is not None and simple.text else None,
        record_delimiter=next((r.text for r in children(fmt, "recordDelimiter") if r.text), None),
        quote_character=text_of(fmt, "simpleDelimited", "quoteCharacter"),
        orientation=text_of(fmt, "attributeOrientation"),
    )


def entity(refs: _Refs, element: Element, *, with_attributes: bool = True) -> EntityMetadata:
    physical = child(element, "physical")
    url = None
    fmt = None
    if physical is not None:
        url = next(
            (squash(u.text) for u in descendants(physical, "url") if u.text and u.text.strip()),
            None,
        )
        data_format = child(physical, "dataFormat")
        if data_format is not None:
            fmt = text_of(data_format, "externallyDefinedFormat", "formatName") or (
                "text" if child(data_format, "textFormat") is not None else None
            )
    name = text_of(element, "entityName")
    match = _PASTA_ENTITY_RE.search(url or "")
    entity_id = match.group("entity") if match else (pasta_entity_id(name) if name else None)
    out = EntityMetadata(
        entity_id=entity_id,
        name=name,
        entity_type=local(element.tag),
        description=text_of(element, "entityDescription"),
        object_name=text_of(physical, "objectName"),
        format=fmt,
        size=size_bytes(child(physical, "size")) if physical is not None else None,
        number_of_records=_int(text_of(element, "numberOfRecords")),
        text_format=_text_format(physical),
        url=url,
    )
    attribute_list = refs(child(element, "attributeList"))
    if attribute_list is not None:
        raw = list(children(attribute_list, "attribute"))
        out.attributes_total = len(raw)
        if with_attributes:
            out.attributes = [
                a for e in raw[:MAX_ATTRIBUTES] if (a := attribute(refs, e)) is not None
            ]
    return out


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


def _eml_version(root: Element) -> str | None:
    if root.tag.startswith("{"):
        namespace = root.tag[1:].split("}", 1)[0]
        m = re.search(r"eml-(\d+\.\d+\.\d+)", namespace)
        return m.group(1) if m else None
    return None


def entity_elements(dataset: Element) -> list[Element]:
    return [e for e in dataset if local(e.tag) in ENTITY_TYPES]


def project_eml(
    root: Element, *, max_text_chars: int = 2000, entity_attributes: bool = False
) -> EmlProjection:
    """Project a parsed EML document; ``entity_attributes`` keeps each entity's attributes."""
    refs = _Refs(root)
    dataset = next(descendants(root, "dataset"), None)
    if dataset is None:
        dataset = Element("dataset")
    abstract, abstract_cut = cut(prose(child(dataset, "abstract")), max_text_chars)
    keywords, keywords_total = _keywords(dataset)
    creators = _people(refs, children(dataset, "creator"))
    publisher_el = refs(child(dataset, "publisher"))
    maintenance, _ = cut(prose(child(child(dataset, "maintenance"), "description")), 500)
    elements = entity_elements(dataset)
    return EmlProjection(
        eml_version=_eml_version(root),
        title=text_of(dataset, "title"),
        short_name=text_of(dataset, "shortName"),
        abstract=abstract,
        abstract_truncated=abstract_cut,
        keywords=keywords,
        keywords_total=keywords_total,
        pub_date=text_of(dataset, "pubDate"),
        language=text_of(dataset, "language"),
        alternate_identifiers=[
            squash(a.text) for a in children(dataset, "alternateIdentifier") if a.text
        ][:MAX_IDS],
        maintenance=maintenance,
        creators=creators[:MAX_PEOPLE],
        creators_total=len(creators),
        contacts=_people(refs, children(dataset, "contact"))[:MAX_PEOPLE],
        associated_parties=_people(refs, children(dataset, "associatedParty"))[:MAX_PEOPLE],
        publisher=person(publisher_el) if publisher_el is not None else None,
        coverage=coverage(refs, child(dataset, "coverage")),
        methods=methods(refs, child(dataset, "methods"), max_text_chars),
        license=license_of(dataset, max_text_chars),
        project=project(refs, child(dataset, "project")),
        entities=[
            entity(refs, e, with_attributes=entity_attributes) for e in elements[:MAX_ENTITIES]
        ],
        entities_total=len(elements),
    )


__all__ = [
    "Annotation",
    "Attribute",
    "Code",
    "Coverage",
    "EmlProjection",
    "EntityMetadata",
    "Funding",
    "GeographicCoverage",
    "KeywordSet",
    "License",
    "Methods",
    "Person",
    "Project",
    "Taxon",
    "TemporalCoverage",
    "TextFormat",
    "cut",
    "entity",
    "project_eml",
]
