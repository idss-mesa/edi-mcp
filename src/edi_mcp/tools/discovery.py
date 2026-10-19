"""Discovery: ``edi_search_packages``, ``edi_list_scopes``, ``edi_list_identifiers`` and
``edi_list_revisions``.

Each works on both backends (DESIGN.md D1): PASTA with a key, DataONE without.
Scope inputs accept exact scopes, LTER site codes and names (D9); resolved
names are echoed in ``resolved``.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, model_validator

from edi_mcp.context import ToolContext
from edi_mcp.edi.backends import (
    BoundingBox,
    PastaBackend,
    SearchQuery,
    backend_for,
)
from edi_mcp.edi.backends.base import BULK_SCOPES, pick_revision
from edi_mcp.edi.scopes import ScopeKind, load_scopes, resolve_reference, resolve_scope
from edi_mcp.errors import ToolError
from edi_mcp.models.common import EdiInput, EdiOutput, Page, Resolved, ToolResultBase
from edi_mcp.registry import register_tool
from edi_mcp.tools._common import merge_notes, paginate, portal_url, source

MAX_AUTHORS = 5
MAX_KEYWORDS = 10

SCOPE_FIELD = (
    "A scope (knb-lter-jrn), LTER site code (JRN) or scope name or location "
    "('Jornada', 'Hubbard Brook'); see edi_list_scopes."
)


def _not_replicated_note(ctx: ToolContext, scope: str) -> list[str]:
    """For an empty DataONE answer: the snapshot says whether DataONE replicated the scope."""
    snapshot = load_scopes()
    record = snapshot.get(scope)
    if ctx.backend == "dataone" and record is not None and not record.dataone_replicated:
        return [
            f"DataONE held no replica of scope {scope} on {snapshot.as_of}; set EDI_API_KEY to "
            "read it from PASTA."
        ]
    return []


# ---------------------------------------------------------------------------
# edi_search_packages
# ---------------------------------------------------------------------------


class SearchPackagesIn(EdiInput):
    query: str | None = Field(
        None,
        max_length=500,
        description='Free text over titles, keywords and abstracts (words, "phrases", '
        "AND/OR/NOT). Omit to browse with filters only.",
    )
    scope: str | None = Field(None, max_length=100, description=f"Only this scope. {SCOPE_FIELD}")
    author: str | None = Field(
        None, max_length=100, description="A creator's last name, e.g. 'Likens' (any case)."
    )
    start_year: int | None = Field(
        None, ge=1000, le=2200, description="Temporal coverage reaches this year or later."
    )
    end_year: int | None = Field(
        None, ge=1000, le=2200, description="Temporal coverage starts in this year or earlier."
    )
    bbox: list[float] | None = Field(
        None,
        min_length=4,
        max_length=4,
        description="[west, south, east, north] in decimal degrees; geographic coverage must "
        "intersect it. west <= east (no antimeridian crossing).",
    )
    sort: Literal["relevance", "newest", "oldest"] = Field(
        "relevance",
        description="relevance, or publication date: newest or oldest (oldest lists undated "
        "packages first).",
    )
    include_bulk: bool = Field(
        False,
        description=f"Include the generated bulk scopes ({', '.join(BULK_SCOPES)}; ~36k records) "
        "when no scope is given.",
    )
    limit: int = Field(10, ge=1, le=50, description="Packages per page (1-50).")
    offset: int = Field(0, ge=0, le=10_000, description="Index of the first result (paging).")

    @model_validator(mode="after")
    def _check(self) -> SearchPackagesIn:
        if (
            self.start_year is not None
            and self.end_year is not None
            and self.start_year > self.end_year
        ):
            raise ValueError("start_year is after end_year")
        if self.bbox is not None:
            west, south, east, north = self.bbox
            if not (-180 <= west <= 180 and -180 <= east <= 180):
                raise ValueError("bbox longitudes must be within -180..180")
            if not (-90 <= south <= 90 and -90 <= north <= 90):
                raise ValueError("bbox latitudes must be within -90..90")
            if south > north:
                raise ValueError("bbox south is north of north")
            if west > east:
                raise ValueError(
                    "bbox west is east of east; split an antimeridian-crossing box into two"
                )
        return self


class PackageHit(EdiOutput):
    package_id: str = Field(description="scope.identifier.revision")
    title: str | None = None
    pub_date: str | None = Field(None, description="Publication year (PASTA) or date (DataONE).")
    doi: str | None = None
    begin_date: str | None = Field(None, description="Start of temporal coverage.")
    end_date: str | None = Field(None, description="End of temporal coverage.")
    authors: list[str] = Field(default_factory=list, description=f"First {MAX_AUTHORS} creators.")
    more_authors: int | None = Field(None, description="Creators not listed in authors.")
    keywords: list[str] = Field(default_factory=list, description=f"First {MAX_KEYWORDS}.")
    portal_url: str = Field(description="EDI Data Portal landing page.")


class SearchPackagesResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "items"

    items: list[PackageHit]
    page: Page
    total_exact: bool = Field(
        description="False on DataONE: page.total is an upper bound (superseded revisions are "
        "counted, then collapsed to one hit per package)."
    )


@register_tool(
    "edi_search_packages",
    title="Search EDI data packages",
    description=(
        "Search EDI/LTER data packages by free text, scope (exact, LTER site code or name such "
        "as 'Jornada'), creator last name, temporal overlap (start_year/end_year) and bounding "
        "box; sort by relevance or publication date; paginated (offset/limit). Returns the "
        "newest revision of each package with title, DOI, coverage dates, creators and "
        "keywords. Bulk generated scopes are excluded unless include_bulk=true. Next: call "
        "edi_get_package or edi_get_metadata with a packageId."
    ),
    input_model=SearchPackagesIn,
    output_model=SearchPackagesResult,
    surface="discovery",
    endpoints=["GET pasta.lternet.edu/package/search/eml", "GET cn.dataone.org/cn/v2/query/solr/"],
)
async def edi_search_packages(args: SearchPackagesIn, ctx: ToolContext) -> SearchPackagesResult:
    resolved: list[Resolved] = []
    scope = None
    if args.scope:
        scope, res = resolve_scope(args.scope)
        resolved += [res] if res else []
    backend = backend_for(ctx)
    query = SearchQuery(
        text=args.query,
        scope=scope,
        offset=args.offset,
        limit=args.limit,
        exclude_bulk=not args.include_bulk,
        author=args.author,
        start_year=args.start_year,
        end_year=args.end_year,
        bbox=BoundingBox(*args.bbox) if args.bbox else None,
        sort=args.sort,
    )
    result = await backend.search(query)
    items = [
        PackageHit(
            package_id=h.package.package_id,
            title=h.title,
            pub_date=h.pub_date,
            doi=h.doi,
            begin_date=h.begin_date,
            end_date=h.end_date,
            authors=h.authors[:MAX_AUTHORS],
            more_authors=len(h.authors) - MAX_AUTHORS if len(h.authors) > MAX_AUTHORS else None,
            keywords=h.keywords[:MAX_KEYWORDS],
            portal_url=portal_url(ctx, h.package),
        )
        for h in result.hits
    ]
    # Advance by the rows requested, not the hits kept: DataONE pages are de-duplicated,
    # so offset + len(items) would re-read rows already consumed.
    consumed = args.offset + args.limit
    more = result.total is not None and result.total > consumed
    page = Page(
        total=result.total,
        returned=len(items),
        offset=args.offset,
        limit=args.limit,
        truncated=more,
        next_offset=consumed if more else None,
        truncated_reason="limit" if more else None,
    )
    notes = list(backend.notes)
    if not result.total_exact:
        notes.append(
            "DataONE counts superseded revisions it has not marked obsolete, so page.total is an "
            "upper bound and a page can hold fewer than limit packages; a package can recur on a "
            "later page at a higher revision."
        )
    if scope and not items:
        notes += _not_replicated_note(ctx, scope)
    if args.sort == "oldest":
        notes.append("sort=oldest lists packages without a publication date first.")
    steps: list[str] = []
    if items:
        first = items[0].package_id
        steps.append(f"edi_get_package(package='{first}') for its DOI, entities and size")
        steps.append(
            f"edi_list_revisions(package='{result.hits[0].package.series}') for every revision"
        )
    else:
        steps.append("Broaden the query: drop filters, or check the scope with edi_list_scopes")
    if page.next_offset is not None:
        steps.append(f"edi_search_packages(..., offset={page.next_offset}) for the next page")
    return SearchPackagesResult(
        items=items,
        page=page,
        total_exact=result.total_exact,
        resolved=resolved,
        notes=merge_notes(notes),
        next_steps=steps,
        source=source(ctx, derived=["items.portalUrl", "items.moreAuthors"]),
    )


# ---------------------------------------------------------------------------
# edi_list_scopes
# ---------------------------------------------------------------------------


class ListScopesIn(EdiInput):
    kind: ScopeKind | None = Field(
        None,
        description="Only one kind: lter (LTER sites), edi (general EDI submissions), bulk "
        "(generated; excluded from search by default), project, agency or other.",
    )


class ScopeInfo(EdiOutput):
    scope: str
    name: str | None = Field(None, description="Absent where no name is verified.")
    kind: ScopeKind | Literal["unknown"] = Field(
        description="unknown = listed by PASTA but newer than edi-mcp's snapshot."
    )
    site_code: str | None = Field(None, description="LTER site code (resolves to this scope).")
    location: str | None = None
    pasta_packages: int | None = Field(
        None, description="Packages (newest revisions) in PASTA on the snapshot date."
    )
    dataone_packages: int | None = Field(
        None,
        description="DataONE metadata records on the snapshot date (an upper bound); 0 = not "
        "replicated, so it needs EDI_API_KEY.",
    )


class ListScopesResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "scopes"

    scopes: list[ScopeInfo]
    page: Page
    live: bool = Field(
        description="True when PASTA listed the scopes just now; false = edi-mcp's snapshot."
    )
    snapshot_as_of: str = Field(description="Date of the snapshot that supplies names and counts.")


@register_tool(
    "edi_list_scopes",
    title="List EDI scopes",
    description=(
        "List the repository's scopes (knb-lter-hbr, edi, ...) with name, kind, LTER site code, "
        "location and package counts on PASTA and DataONE. With an API key the list comes live "
        "from PASTA; without one it is edi-mcp's dated snapshot (also edi://reference/scopes). "
        "Scope arguments elsewhere also accept these site codes and names. Next: call "
        "edi_search_packages(scope=...) or edi_list_identifiers(scope=...)."
    ),
    input_model=ListScopesIn,
    output_model=ListScopesResult,
    surface="discovery",
    endpoints=["GET pasta.lternet.edu/package/eml"],
)
async def edi_list_scopes(args: ListScopesIn, ctx: ToolContext) -> ListScopesResult:
    snapshot = load_scopes()
    backend = backend_for(ctx)
    notes: list[str] = []
    live = isinstance(backend, PastaBackend)
    if isinstance(backend, PastaBackend):
        names = await backend.list_scopes()
        dropped = [r.scope for r in snapshot.records if r.scope not in set(names)]
        if dropped:
            notes.append(f"In the snapshot but no longer listed by PASTA: {', '.join(dropped)}.")
    else:
        names = [r.scope for r in snapshot.records]
        notes.append(
            f"edi-mcp's scope snapshot of {snapshot.as_of} (no EDI API key, and DataONE has no "
            "scope listing); scopes created since then are missing."
        )
    scopes: list[ScopeInfo] = []
    for name in sorted(names):
        record = snapshot.get(name)
        if record is None:
            scopes.append(ScopeInfo(scope=name, kind="unknown"))
            continue
        scopes.append(
            ScopeInfo(
                scope=record.scope,
                name=record.name,
                kind=record.kind,
                site_code=record.site_code,
                location=record.location,
                pasta_packages=record.pasta_packages,
                dataone_packages=record.dataone_packages,
            )
        )
    if args.kind is not None:
        scopes = [s for s in scopes if s.kind == args.kind]
    page = Page(
        total=len(scopes), returned=len(scopes), offset=0, limit=len(scopes), truncated=False
    )
    if live:
        notes.append(f"Names and package counts come from the {snapshot.as_of} snapshot.")
    return ListScopesResult(
        scopes=scopes,
        page=page,
        live=live,
        snapshot_as_of=snapshot.as_of,
        notes=notes,
        next_steps=[
            "edi_search_packages(scope='knb-lter-jrn', query='...') to search one scope",
            "edi_list_identifiers(scope='knb-lter-jrn') to list its package identifiers",
        ],
        source=source(ctx, derived=["scopes.name", "scopes.kind", "scopes.siteCode"]),
    )


# ---------------------------------------------------------------------------
# edi_list_identifiers
# ---------------------------------------------------------------------------


class ListIdentifiersIn(EdiInput):
    scope: str = Field(min_length=1, max_length=100, description=SCOPE_FIELD)
    limit: int = Field(200, ge=1, le=1000, description="Identifiers per page (1-1000).")
    offset: int = Field(0, ge=0, description="Index of the first identifier (paging).")


class ListIdentifiersResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "identifiers"

    scope: str
    identifiers: list[int] = Field(description="Package identifiers in ascending order.")
    page: Page


@register_tool(
    "edi_list_identifiers",
    title="List package identifiers in a scope",
    description=(
        "List the package identifiers in one scope, ascending and paginated (offset/limit). The "
        "scope may be exact (knb-lter-hbr), an LTER site code (HBR) or a name ('Hubbard Brook'). "
        "Identifiers are numbers; a package is scope.identifier.revision. Next: call "
        "edi_list_revisions(package='scope.identifier') for one identifier's revisions."
    ),
    input_model=ListIdentifiersIn,
    output_model=ListIdentifiersResult,
    surface="discovery",
    endpoints=["GET pasta.lternet.edu/package/eml/{scope}", "GET cn.dataone.org/cn/v2/query/solr/"],
)
async def edi_list_identifiers(args: ListIdentifiersIn, ctx: ToolContext) -> ListIdentifiersResult:
    scope, res = resolve_scope(args.scope)
    backend = backend_for(ctx)
    identifiers = await backend.list_identifiers(scope)
    if not identifiers:
        raise ToolError(
            "not_found",
            f"Scope {scope!r} has no packages.",
            details={"identifier": scope, "backend": backend.name},
            hint="Check the scope with edi_list_scopes.",
        )
    page_items, page = paginate(identifiers, offset=args.offset, limit=args.limit)
    steps = []
    if page_items:
        steps.append(f"edi_list_revisions(package='{scope}.{page_items[0]}')")
    if page.next_offset is not None:
        steps.append(f"edi_list_identifiers(scope='{scope}', offset={page.next_offset})")
    return ListIdentifiersResult(
        scope=scope,
        identifiers=page_items,
        page=page,
        resolved=[res] if res else [],
        notes=list(backend.notes),
        next_steps=steps,
        source=source(ctx),
    )


# ---------------------------------------------------------------------------
# edi_list_revisions
# ---------------------------------------------------------------------------


class ListRevisionsIn(EdiInput):
    package: str = Field(
        min_length=1,
        max_length=500,
        description="A package series or any revision of it: knb-lter-hbr.14, "
        "knb-lter-hbr.14.22, knb-lter-hbr/14, a DOI, a portal or PASTA URL; the scope may be "
        "a site code or name (jrn.210548103).",
    )


class ListRevisionsResult(ToolResultBase):
    series: str = Field(description="scope.identifier")
    scope: str
    identifier: int
    revisions: list[int] = Field(description="Every revision, ascending.")
    newest: int
    oldest: int
    newest_package_id: str


@register_tool(
    "edi_list_revisions",
    title="List the revisions of a package",
    description=(
        "List every revision of one data package (scope.identifier), ascending, with the newest "
        "and oldest. Accepts a series (knb-lter-hbr.14), any revision, a DOI, a portal or PASTA "
        "URL, and site codes or scope names in place of the scope. Without an API key DataONE "
        "answers and can lag new revisions. Next: call edi_get_package(package=newestPackageId)."
    ),
    input_model=ListRevisionsIn,
    output_model=ListRevisionsResult,
    surface="discovery",
    endpoints=[
        "GET pasta.lternet.edu/package/eml/{scope}/{identifier}",
        "GET pasta.lternet.edu/package/search/eml",
        "GET cn.dataone.org/cn/v2/query/solr/",
        "GET cn.dataone.org/cn/v2/object/{pid}",
    ],
)
async def edi_list_revisions(args: ListRevisionsIn, ctx: ToolContext) -> ListRevisionsResult:
    ref, resolved = resolve_reference(args.package)
    backend = backend_for(ctx)
    if ref.doi is not None:
        package = await backend.resolve_doi(ref.doi)
        resolved.append(
            Resolved(field="package", input=args.package, code=package.package_id, confidence=1.0)
        )
    elif ref.package is not None:
        package = ref.package
    else:  # pragma: no cover - resolve_reference returns a package or a DOI
        raise ToolError("invalid_argument", f"{args.package!r} names no package.")
    revisions = await backend.list_revisions(package.scope, package.identifier)
    newest = pick_revision(revisions, "newest")
    oldest = pick_revision(revisions, "oldest")
    if newest is None or oldest is None:
        hint = (
            "Check the scope and identifier with edi_list_identifiers."
            if isinstance(backend, PastaBackend)
            else "DataONE can lag EDI or skip a scope; set EDI_API_KEY to read PASTA directly."
        )
        raise ToolError(
            "not_found",
            f"No revisions of {package.series} were found.",
            details={"identifier": package.series, "backend": backend.name},
            hint=hint,
        )
    notes = list(backend.notes)
    if package.revision is not None and package.revision not in revisions:
        notes.append(f"Revision {package.revision} is not among the listed revisions.")
    newest_id = package.with_revision(newest).package_id
    return ListRevisionsResult(
        series=package.series,
        scope=package.scope,
        identifier=package.identifier,
        revisions=revisions,
        newest=newest,
        oldest=oldest,
        newest_package_id=newest_id,
        resolved=resolved,
        notes=notes,
        next_steps=[f"edi_get_package(package='{newest_id}')"],
        source=source(ctx),
    )
