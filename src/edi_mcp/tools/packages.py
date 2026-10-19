"""Package, metadata and entity tools: ``edi_get_package``, ``edi_get_metadata`` and
``edi_list_entities``.

Each call fetches the EML once, parses it once (defusedxml) and projects it
(:mod:`edi_mcp.projections.eml`); the backend adds what the EML cannot say
authoritatively: PASTA's byte sizes and checksums, or DataONE's index.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Literal
from xml.etree.ElementTree import Element

from pydantic import Field, field_validator

from edi_mcp.context import ToolContext
from edi_mcp.edi.backends import (
    DataOneBackend,
    EntityInfo,
    PastaBackend,
    ResolvedPackage,
    backend_for,
    resolve_package,
)
from edi_mcp.edi.eml import entity_refs
from edi_mcp.edi.pid import Doi
from edi_mcp.edi.scopes import load_scopes
from edi_mcp.edi.xml import parse_xml
from edi_mcp.errors import ToolError
from edi_mcp.models.common import EdiInput, EdiOutput, Page, Resolved, ToolResultBase
from edi_mcp.projections.eml import (
    Attribute,
    Coverage,
    EmlProjection,
    EntityMetadata,
    KeywordSet,
    License,
    Methods,
    Person,
    Project,
    TextFormat,
    cut,
    project_eml,
)
from edi_mcp.registry import register_tool
from edi_mcp.tools._common import merge_notes, paginate, portal_url, source

MAX_CHECKSUMS = 25
MAX_PACKAGE_ENTITIES = 100
PACKAGE_FIELD = (
    "A package: knb-lter-hbr.14.22, knb-lter-hbr.14 (newest unless revision is set), a DOI, "
    "or a portal or PASTA URL; the scope may be a site code or name (jrn.210548103)."
)
REVISION_FIELD = "Revision when package names none: a number, 'newest' (default) or 'oldest'."
Section = Literal["overview", "people", "coverage", "methods", "rights", "project", "entities"]
SECTIONS: tuple[Section, ...] = (
    "overview",
    "people",
    "coverage",
    "methods",
    "rights",
    "project",
    "entities",
)
RevisionFrom = Literal["given", "newest", "oldest", "doi"]


class PackageArgs(EdiInput):
    package: str = Field(min_length=1, max_length=500, description=PACKAGE_FIELD)
    revision: int | Literal["newest", "oldest"] | None = Field(None, description=REVISION_FIELD)

    @field_validator("revision")
    @classmethod
    def _non_negative(cls, value: int | str | None) -> int | str | None:
        if isinstance(value, int) and value < 0:
            raise ValueError("revision must be 0 or more")
        return value


# ---------------------------------------------------------------------------
# Shared loading
# ---------------------------------------------------------------------------


@dataclass
class Loaded:
    backend: PastaBackend | DataOneBackend
    resolved: ResolvedPackage
    eml: EmlProjection
    root: Element
    echoes: list[Resolved] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: The EML document as fetched (edi_download_entities saves it beside the data).
    body: bytes = b""


async def load(
    args: PackageArgs,
    ctx: ToolContext,
    *,
    max_text_chars: int = 2000,
    entity_attributes: bool = False,
) -> Loaded:
    """Resolve the package, fetch its EML once and project it."""
    backend = backend_for(ctx)
    resolved = await resolve_package(backend, args.package, args.revision)
    package = resolved.package
    echoes = list(resolved.resolved)
    if resolved.raw.strip() != package.package_id:
        echoes.append(
            Resolved(field="package", input=args.package, code=package.package_id, confidence=1.0)
        )
    body = await backend.read_eml(package)
    root = parse_xml(
        body,
        source=backend.metadata_pid(package),
        service="PASTA" if isinstance(backend, PastaBackend) else "DataONE",
    )
    projection = project_eml(
        root, max_text_chars=max_text_chars, entity_attributes=entity_attributes
    )
    notes = dataone_newest_note(backend.name, resolved)
    return Loaded(backend, resolved, projection, root, echoes, notes, body)


def dataone_newest_note(backend: str, resolved: ResolvedPackage) -> list[str]:
    """Without a key, 'newest' is DataONE's newest, which can lag PASTA's (D16)."""
    if resolved.revision_from == "newest" and backend == "dataone":
        return [
            f"Revision {resolved.package.revision} is the newest DataONE holds; PASTA can "
            "hold newer ones (set EDI_API_KEY to be sure)."
        ]
    return []


def _summary(meta: EntityMetadata, info: EntityInfo | None) -> EntitySummary:
    return EntitySummary(
        entity_id=(info.entity_id if info else None) or meta.entity_id,
        name=meta.name or (info.name if info else None),
        entity_type=meta.entity_type,
        object_name=meta.object_name or (info.object_name if info else None),
        format=meta.format or (info.format_id if info else None),
        size=(info.size if info and info.size is not None else meta.size),
    )


def merge_entities(
    infos: list[EntityInfo], metas: list[EntityMetadata]
) -> tuple[list[tuple[EntityMetadata | None, EntityInfo | None]], list[str]]:
    """Pair backend entities with EML entities: by entity id, then by exact name.

    PASTA's id is the MD5 of the entity name (verified on two packages), so the
    id normally matches; whatever pairs neither way is kept and reported.
    """
    by_id = {m.entity_id: m for m in metas if m.entity_id}
    by_name = {m.name: m for m in metas if m.name}
    used: set[int] = set()
    pairs: list[tuple[EntityMetadata | None, EntityInfo | None]] = []
    unmatched_infos: list[str] = []
    for info in infos:
        meta = by_id.get(info.entity_id) or (by_name.get(info.name) if info.name else None)
        if meta is None or id(meta) in used:
            unmatched_infos.append(info.name or info.entity_id)
            pairs.append((None, info))
            continue
        used.add(id(meta))
        pairs.append((meta, info))
    extra = [m for m in metas if id(m) not in used]
    pairs.extend((m, None) for m in extra)
    notes = []
    if unmatched_infos and infos:
        notes.append(
            "Listed by the repository but not matched to an EML entity: "
            + ", ".join(unmatched_infos[:10])
            + "."
        )
    if extra and infos:
        notes.append(
            "Declared in the EML but not listed by the repository: "
            + ", ".join(m.name or m.entity_type for m in extra[:10])
            + "."
        )
    return pairs, notes


# ---------------------------------------------------------------------------
# Output pieces
# ---------------------------------------------------------------------------


class EntitySummary(EdiOutput):
    entity_id: str | None = Field(None, description="PASTA entity id (MD5 of the name).")
    name: str | None = None
    entity_type: str | None = Field(None, description="dataTable, otherEntity, spatialRaster, …")
    object_name: str | None = Field(None, description="File name.")
    format: str | None = None
    size: int | None = Field(
        None, description="Bytes: PASTA's count with a key, else DataONE's index or the EML."
    )


class EntityDetail(EntitySummary):
    description: str | None = None
    number_of_records: int | None = None
    sha1: str | None = Field(None, description="SHA-1 checksum, lower-case hex.")
    text_format: TextFormat | None = None
    attributes: list[Attribute] | None = Field(
        None, description="Columns; null when trimmed to fit the result budget."
    )
    attributes_total: int = 0
    data_url: str | None = Field(None, description="PASTA data URL (needs an EDI API key).")
    anonymous_url: str | None = Field(
        None,
        description="The same object on its DataONE member node, usually readable without a "
        "key; absent for scopes DataONE does not replicate, and DataONE may lag new revisions.",
    )


# ---------------------------------------------------------------------------
# edi_get_package
# ---------------------------------------------------------------------------


class GetPackageIn(PackageArgs):
    pass


ENTITIES_NEXT_STEP = (
    "call edi_list_entities(package=..., offset={next_offset}) for the remaining entities."
)


class PackageResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "entities"
    budget_next_step: ClassVar[str | None] = ENTITIES_NEXT_STEP

    package_id: str
    series: str = Field(description="scope.identifier")
    revision: int
    revision_from: RevisionFrom = Field(
        description="How the revision was chosen: given, newest, oldest, or the DOI's."
    )
    newest_revision: int | None = Field(
        None, description="Newest revision on the serving backend (DataONE can lag PASTA)."
    )
    is_newest: bool | None = Field(None, description="revision == newestRevision.")
    title: str | None = None
    pub_date: str | None = None
    doi: str | None = None
    doi_url: str | None = None
    portal_url: str
    metadata_url: str = Field(description="PASTA EML URL (needs an EDI API key).")
    creators: list[str] = Field(default_factory=list)
    creators_total: int = 0
    license: License | None = None
    entity_count: int = Field(description="All entities, including any not listed below.")
    total_bytes: int | None = Field(None, description="Sum of known entity sizes (all entities).")
    entities: list[EntitySummary] = Field(
        description=f"The first {MAX_PACKAGE_ENTITIES}; edi_list_entities pages through all."
    )


@register_tool(
    "edi_get_package",
    title="Get an EDI data package",
    description=(
        "Overview of one package revision: title, publication date, creators, license, DOI, "
        "portal and metadata URLs, whether it is the newest revision, and its data entities "
        "with sizes and the total. Accepts package ids, series (newest unless revision is set), "
        "DOIs, portal or PASTA URLs, and site codes or scope names for the scope. Next: call "
        "edi_get_metadata for the full description or edi_list_entities for columns."
    ),
    input_model=GetPackageIn,
    output_model=PackageResult,
    surface="packages",
    endpoints=[
        "GET pasta.lternet.edu/package/metadata/eml/{scope}/{id}/{rev}",
        "GET pasta.lternet.edu/package/name/eml/{scope}/{id}/{rev}",
        "GET pasta.lternet.edu/package/data/size/eml/{scope}/{id}/{rev}",
        "GET pasta.lternet.edu/package/doi/eml/{scope}/{id}/{rev}",
        "GET pasta.lternet.edu/package/eml/{scope}/{id}",
        "GET gmn.lternet.edu/mn/v2/object/{pid}",
        "GET cn.dataone.org/cn/v2/query/solr/",
        "GET cite.edirepository.org/cite/{packageId}",
    ],
)
async def edi_get_package(args: GetPackageIn, ctx: ToolContext) -> PackageResult:
    loaded = await load(args, ctx)
    backend, package, eml = loaded.backend, loaded.resolved.package, loaded.eml
    refs = entity_refs(loaded.root, source=backend.metadata_pid(package))
    infos = await backend.list_entities(package, refs)
    pairs, merge_notes_ = merge_entities(infos, eml.entities)
    entities: list[EntitySummary] = []
    for meta, info in pairs:
        if meta is not None:
            entities.append(_summary(meta, info))
        elif info is not None:
            entities.append(EntitySummary(entity_id=info.entity_id, name=info.name, size=info.size))
    sizes = [e.size for e in entities if e.size is not None]
    doi = await backend.package_doi(package)
    if loaded.resolved.revision_from == "newest":
        newest: int | None = package.revision
    else:
        revisions = await backend.list_revisions(package.scope, package.identifier)
        newest = max(revisions) if revisions else None
    revision = package.revision if package.revision is not None else 0
    notes = merge_notes(loaded.notes, backend.notes, merge_notes_)
    if newest is not None and revision < newest:
        notes.append(f"A newer revision exists: {package.with_revision(newest).package_id}.")
    if isinstance(backend, DataOneBackend) and loaded.resolved.revision_from != "newest":
        notes.append("newestRevision is the newest DataONE holds; PASTA can hold newer ones.")
    steps = [
        f"edi_get_metadata(package='{package.package_id}') for abstract, coverage and methods",
        f"edi_list_entities(package='{package.package_id}') for columns, units and checksums",
        f"edi_get_citation(package='{package.package_id}') to cite it",
    ]
    if len(entities) > MAX_PACKAGE_ENTITIES:
        notes.append(f"Listing the first {MAX_PACKAGE_ENTITIES} of {len(entities)} entities.")
        steps.insert(
            0,
            f"edi_list_entities(package='{package.package_id}', offset={MAX_PACKAGE_ENTITIES}, "
            "include_attributes=false) for the remaining entities",
        )
    lic = eml.license
    if lic is not None and lic.text:
        text, truncated = cut(lic.text, 300)
        lic = lic.model_copy(update={"text": text, "truncated": truncated or lic.truncated})
    doi_md5 = doi.rsplit("/", 1)[-1] if doi else None
    return PackageResult(
        package_id=package.package_id,
        series=package.series,
        revision=revision,
        revision_from=loaded.resolved.revision_from,
        newest_revision=newest,
        is_newest=(revision == newest) if newest is not None else None,
        title=eml.title,
        pub_date=eml.pub_date,
        doi=doi,
        doi_url=Doi(doi_md5).url if doi_md5 and len(doi_md5) == 32 else None,
        portal_url=portal_url(ctx, package),
        metadata_url=backend.metadata_pid(package),
        creators=[c.name for c in eml.creators if c.name],
        creators_total=eml.creators_total,
        license=lic,
        entity_count=len(entities),
        total_bytes=sum(sizes) if sizes else None,
        entities=entities[:MAX_PACKAGE_ENTITIES],
        resolved=loaded.echoes,
        notes=notes,
        next_steps=steps,
        source=source(ctx, derived=["portalUrl", "totalBytes", "isNewest"]),
    )


# ---------------------------------------------------------------------------
# edi_get_metadata
# ---------------------------------------------------------------------------


class GetMetadataIn(PackageArgs):
    include: list[Section] = Field(
        default_factory=lambda: list(SECTIONS),
        min_length=1,
        description="Sections to return: overview (abstract, keywords, dates), people, "
        "coverage (geographic, temporal, taxonomic), methods, rights, project (funding), "
        "entities. Default: all.",
    )
    max_text_chars: int = Field(
        2000, ge=200, le=20_000, description="Cut abstract, methods and rights to this length."
    )


class MetadataResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "entities"
    budget_next_step: ClassVar[str | None] = ENTITIES_NEXT_STEP

    package_id: str
    revision_from: RevisionFrom
    eml_version: str | None = None
    title: str | None = None
    short_name: str | None = None
    abstract: str | None = None
    abstract_truncated: bool | None = None
    keywords: list[KeywordSet] | None = None
    keywords_total: int | None = None
    pub_date: str | None = None
    language: str | None = None
    alternate_identifiers: list[str] | None = None
    maintenance: str | None = None
    creators: list[Person] | None = None
    creators_total: int | None = None
    contacts: list[Person] | None = None
    associated_parties: list[Person] | None = None
    publisher: Person | None = None
    coverage: Coverage | None = None
    methods: Methods | None = None
    license: License | None = None
    project: Project | None = None
    entities: list[EntitySummary] | None = None
    entities_total: int | None = None


@register_tool(
    "edi_get_metadata",
    title="Read a package's EML metadata",
    description=(
        "The package's EML, projected to compact sections: overview (abstract, keywords, "
        "dates), people (creators, contacts with ORCIDs), coverage (bounding boxes, date "
        "ranges, taxa), methods, rights and license, project and funding, and entities. Choose "
        "sections with include; long text is cut at max_text_chars and lists are capped with "
        "totals. Next: call edi_list_entities for column definitions, units and codes."
    ),
    input_model=GetMetadataIn,
    output_model=MetadataResult,
    surface="packages",
    endpoints=[
        "GET pasta.lternet.edu/package/metadata/eml/{scope}/{id}/{rev}",
        "GET gmn.lternet.edu/mn/v2/object/{pid}",
        "GET pasta.lternet.edu/package/eml/{scope}/{id}",
        "GET cn.dataone.org/cn/v2/query/solr/",
    ],
)
async def edi_get_metadata(args: GetMetadataIn, ctx: ToolContext) -> MetadataResult:
    loaded = await load(args, ctx, max_text_chars=args.max_text_chars)
    eml, package = loaded.eml, loaded.resolved.package
    want = set(args.include)
    out = MetadataResult(
        package_id=package.package_id,
        revision_from=loaded.resolved.revision_from,
        eml_version=eml.eml_version,
        title=eml.title,
        short_name=eml.short_name,
        resolved=loaded.echoes,
        notes=merge_notes(loaded.notes, loaded.backend.notes),
        next_steps=[
            f"edi_list_entities(package='{package.package_id}') for columns, units and codes",
            f"edi_get_citation(package='{package.package_id}') to cite it",
        ],
        source=source(ctx),
    )
    if "overview" in want:
        out.abstract, out.abstract_truncated = eml.abstract, eml.abstract_truncated
        out.keywords, out.keywords_total = eml.keywords, eml.keywords_total
        out.pub_date, out.language = eml.pub_date, eml.language
        out.alternate_identifiers = eml.alternate_identifiers
        out.maintenance = eml.maintenance
    if "people" in want:
        out.creators, out.creators_total = eml.creators, eml.creators_total
        out.contacts, out.associated_parties = eml.contacts, eml.associated_parties
        out.publisher = eml.publisher
    if "coverage" in want:
        out.coverage = eml.coverage
    if "methods" in want:
        out.methods = eml.methods
    if "rights" in want:
        out.license = eml.license
    if "project" in want:
        out.project = eml.project
    if "entities" in want:
        out.entities = [_summary(m, None) for m in eml.entities]
        out.entities_total = eml.entities_total
    truncated = [
        name
        for name, cut_ in (
            ("abstract", out.abstract_truncated),
            ("methods", out.methods.truncated if out.methods else False),
            ("rights", out.license.truncated if out.license else False),
        )
        if cut_
    ]
    if truncated:
        out.notes.append(
            f"Cut at {args.max_text_chars} characters: {', '.join(truncated)}; raise max_text_chars "
            "for more."
        )
    return out


# ---------------------------------------------------------------------------
# edi_list_entities
# ---------------------------------------------------------------------------


class ListEntitiesIn(PackageArgs):
    entity: str | None = Field(
        None,
        max_length=300,
        description="Only this entity: its id, name or file name (case-insensitive).",
    )
    include_attributes: bool = Field(
        True, description="Return each entity's columns (definitions, units, codes)."
    )
    include_checksums: bool = Field(
        False,
        description=f"Fetch missing SHA-1 checksums (one request per entity, at most "
        f"{MAX_CHECKSUMS}).",
    )
    limit: int = Field(50, ge=1, le=200, description="Entities per page (1-200).")
    offset: int = Field(0, ge=0, description="Index of the first entity (paging).")


class ListEntitiesResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "entities"
    budget_elide_fields: ClassVar[tuple[str, ...]] = ("attributes",)
    budget_elide_flag: ClassVar[str | None] = "attributes_elided"

    package_id: str
    revision_from: RevisionFrom
    entities: list[EntityDetail]
    page: Page
    attributes_elided: bool | None = Field(
        None, description="True when some entities' attributes were dropped to fit the budget."
    )


@dataclass
class EntityRow:
    """One entity with both views: the EML's and the backend's."""

    meta: EntityMetadata | None
    info: EntityInfo | None

    @property
    def entity_id(self) -> str | None:
        return (self.info.entity_id if self.info else None) or (
            self.meta.entity_id if self.meta else None
        )

    @property
    def name(self) -> str | None:
        return (self.meta.name if self.meta else None) or (self.info.name if self.info else None)

    @property
    def object_name(self) -> str | None:
        return (self.meta.object_name if self.meta else None) or (
            self.info.object_name if self.info else None
        )

    @property
    def size(self) -> int | None:
        if self.info is not None and self.info.size is not None:
            return self.info.size
        return self.meta.size if self.meta else None

    def matches(self, wanted: str) -> bool:
        w = wanted.strip().lower()
        return any(
            v is not None and v.lower() == w for v in (self.entity_id, self.name, self.object_name)
        )


async def entity_rows(loaded: Loaded) -> tuple[list[EntityRow], list[str]]:
    """Every entity of the loaded package, EML and backend views merged."""
    backend, package = loaded.backend, loaded.resolved.package
    refs = entity_refs(loaded.root, source=backend.metadata_pid(package))
    infos = await backend.list_entities(package, refs)
    pairs, notes = merge_entities(infos, loaded.eml.entities)
    return [EntityRow(m, i) for m, i in pairs], notes


def pick_entities(
    rows: list[EntityRow], wanted: list[str] | None, package_id: str
) -> list[EntityRow]:
    """The rows ``wanted`` names (id, name or file name, case-insensitive); all when None."""
    if not wanted:
        return list(rows)
    out: list[EntityRow] = []
    missing: list[str] = []
    for value in wanted:
        hit = next((r for r in rows if r.matches(value)), None)
        if hit is None:
            missing.append(value)
        elif hit not in out:
            out.append(hit)
    if missing:
        raise ToolError(
            "not_found",
            f"Package {package_id} has no entity {', '.join(repr(m) for m in missing[:5])}.",
            details={"identifier": missing[0], "packageId": package_id, "missing": missing[:20]},
            hint="Call edi_list_entities to see every entity's id, name and file name.",
        )
    return out


def _matches(detail: EntityDetail, wanted: str) -> bool:
    w = wanted.strip().lower()
    return any(
        v is not None and v.lower() == w
        for v in (detail.entity_id, detail.name, detail.object_name)
    )


@register_tool(
    "edi_list_entities",
    title="List a package's data entities",
    description=(
        "Every data entity (table or file) of one package revision: name, type, file name, "
        "format, byte size, record count, CSV layout and the columns with definitions, storage "
        "types, units, date formats, code lists and missing-value codes; optional SHA-1 "
        "checksums. Gives the PASTA data URL and a DataONE URL readable without a key. Next: "
        "call edi_preview_entity or edi_download_entities with an entityId."
    ),
    input_model=ListEntitiesIn,
    output_model=ListEntitiesResult,
    surface="entities",
    endpoints=[
        "GET pasta.lternet.edu/package/metadata/eml/{scope}/{id}/{rev}",
        "GET pasta.lternet.edu/package/name/eml/{scope}/{id}/{rev}",
        "GET pasta.lternet.edu/package/data/size/eml/{scope}/{id}/{rev}",
        "GET pasta.lternet.edu/package/data/checksum/eml/{scope}/{id}/{rev}/{entity}",
        "GET gmn.lternet.edu/mn/v2/object/{pid}",
        "GET gmn.lternet.edu/mn/v2/meta/{pid}",
        "GET cn.dataone.org/cn/v2/query/solr/",
    ],
)
async def edi_list_entities(args: ListEntitiesIn, ctx: ToolContext) -> ListEntitiesResult:
    loaded = await load(args, ctx, entity_attributes=args.include_attributes)
    backend, package, eml = loaded.backend, loaded.resolved.package, loaded.eml
    refs = entity_refs(loaded.root, source=backend.metadata_pid(package))
    infos = await backend.list_entities(package, refs)
    pairs, notes = merge_entities(infos, eml.entities)
    record = load_scopes().get(package.scope)
    replicated = record is None or record.dataone_replicated
    details: list[EntityDetail] = []
    for meta, info in pairs:
        base = (
            _summary(meta, info)
            if meta is not None
            else EntitySummary(
                entity_id=info.entity_id if info else None, name=info.name if info else None
            )
        )
        entity_id = base.entity_id
        details.append(
            EntityDetail(
                **base.model_dump(),
                description=meta.description if meta else None,
                number_of_records=meta.number_of_records if meta else None,
                sha1=info.sha1 if info else None,
                text_format=meta.text_format if meta else None,
                attributes=(meta.attributes if meta and args.include_attributes else None),
                attributes_total=meta.attributes_total if meta else 0,
                data_url=backend.data_url(package, entity_id) if entity_id else None,
                anonymous_url=(
                    backend.anonymous_data_url(package, entity_id)
                    if entity_id and replicated
                    else None
                ),
            )
        )
    if args.entity:
        details = [d for d in details if _matches(d, args.entity)]
        if not details:
            raise ToolError(
                "not_found",
                f"Package {package.package_id} has no entity {args.entity!r}.",
                details={"identifier": args.entity, "packageId": package.package_id},
                hint="Call edi_list_entities without entity to see every entity.",
            )
    page_items, page = paginate(details, offset=args.offset, limit=args.limit)
    if args.include_checksums:
        missing = [d for d in page_items if d.sha1 is None and d.entity_id]
        for detail in missing[:MAX_CHECKSUMS]:
            if detail.entity_id is not None:
                detail.sha1 = await backend.entity_checksum(package, detail.entity_id)
        if len(missing) > MAX_CHECKSUMS:
            notes.append(
                f"Checksums fetched for the first {MAX_CHECKSUMS} entities only; page with "
                "offset/limit for the rest."
            )
    steps = []
    if page_items and page_items[0].entity_id:
        first = page_items[0].entity_id
        steps.append(f"edi_preview_entity(package='{package.package_id}', entity='{first}')")
        steps.append(f"edi_download_entities(package='{package.package_id}', entities=['{first}'])")
    if page.next_offset is not None:
        steps.append(
            f"edi_list_entities(package='{package.package_id}', offset={page.next_offset})"
        )
    return ListEntitiesResult(
        package_id=package.package_id,
        revision_from=loaded.resolved.revision_from,
        entities=page_items,
        page=page,
        resolved=loaded.echoes,
        notes=merge_notes(loaded.notes, backend.notes, notes),
        next_steps=steps,
        source=source(ctx, derived=["entities.anonymousUrl", "entities.entityId"]),
    )
