"""PASTA feeds: ``edi_recent_changes`` and ``edi_get_read_counts`` (EDI API key required).

The change feed names the uploader's EDI principal for every entry; edi-mcp
drops it, so no other user's identifier ever reaches a result.
"""

from __future__ import annotations

import datetime as dt
from typing import ClassVar, Literal

from pydantic import Field, field_validator

from edi_mcp.context import ToolContext
from edi_mcp.edi.backends import PastaBackend, backend_for
from edi_mcp.edi.backends.pasta import ChangeKind, ResourceReads
from edi_mcp.edi.scopes import resolve_reference, resolve_scope
from edi_mcp.errors import ToolError
from edi_mcp.models.common import EdiInput, EdiOutput, Page, Resolved, ToolResultBase
from edi_mcp.registry import register_tool
from edi_mcp.tools._common import merge_notes, paginate, source

DEFAULT_DAYS = 7
MAX_WINDOW_DAYS = 92
MAX_REVISIONS = 100


def _pasta(ctx: ToolContext) -> PastaBackend:
    backend = backend_for(ctx)
    if not isinstance(backend, PastaBackend):  # pragma: no cover - the registry requires a key
        raise ToolError("auth_required", "This tool needs an EDI API key.")
    return backend


# ---------------------------------------------------------------------------
# edi_recent_changes
# ---------------------------------------------------------------------------


class ChangesIn(EdiInput):
    from_date: dt.date | None = Field(
        None, description=f"First day (YYYY-MM-DD, UTC); default {DEFAULT_DAYS} days ago."
    )
    to_date: dt.date | None = Field(None, description="Last day (inclusive); default today.")
    scope: str | None = Field(
        None, max_length=100, description="Only this scope: code, LTER site code or name."
    )
    kinds: list[ChangeKind] | None = Field(
        None, description="Only these: insert (new package), update (new revision), delete."
    )
    offset: int = Field(0, ge=0, description="Index of the first change (paging).")
    limit: int = Field(25, ge=1, le=200, description="Changes per page.")

    @field_validator("kinds")
    @classmethod
    def _dedupe(cls, value: list[ChangeKind] | None) -> list[ChangeKind] | None:
        return sorted(set(value)) if value else None


class ChangeOut(EdiOutput):
    package_id: str
    kind: ChangeKind | None = None
    date: str | None = Field(None, description="UTC, ISO 8601.")
    doi: str | None = None


class ChangesResult(ToolResultBase):
    budget_list: ClassVar[str | None] = "changes"

    from_date: str
    to_date: str
    scope: str | None = None
    changes: list[ChangeOut] = Field(description="Newest first.")
    counts: dict[str, int] = Field(description="Changes in the window by kind.")
    page: Page


@register_tool(
    "edi_recent_changes",
    title="List recent repository changes",
    description=(
        "Packages inserted, updated (new revisions) or deleted in PASTA during a date window "
        f"(default the last {DEFAULT_DAYS} days, at most {MAX_WINDOW_DAYS}), optionally for one "
        "scope or kind, newest first, with DOIs. Needs an EDI API key. Next: call "
        "edi_get_package on a packageId."
    ),
    input_model=ChangesIn,
    output_model=ChangesResult,
    surface="feeds",
    endpoints=["GET pasta.lternet.edu/package/changes/eml"],
    requires_key=True,
)
async def edi_recent_changes(args: ChangesIn, ctx: ToolContext) -> ChangesResult:
    backend = _pasta(ctx)
    today = dt.datetime.now(dt.UTC).date()
    end = args.to_date or today
    start = args.from_date or (end - dt.timedelta(days=DEFAULT_DAYS))
    if start > end:
        raise ToolError("invalid_argument", "from_date is after to_date.")
    if (end - start).days > MAX_WINDOW_DAYS:
        raise ToolError(
            "invalid_argument",
            f"The window is {(end - start).days} days; the most is {MAX_WINDOW_DAYS}.",
            hint="Split the period into several calls.",
        )
    echoes: list[Resolved] = []
    scope = None
    if args.scope:
        scope, echo = resolve_scope(args.scope)
        if echo is not None:
            echoes.append(echo)
    # toDate is exclusive upstream; ask for the next day so to_date is inclusive.
    changes = await backend.changes(
        start.isoformat(), (end + dt.timedelta(days=1)).isoformat(), scope
    )
    # Keep the window exact whatever the upstream end-date semantics are.
    first, last = start.isoformat(), end.isoformat()
    changes = [c for c in changes if c.date is None or first <= c.date[:10] <= last]
    counts: dict[str, int] = {}
    for change in changes:
        counts[change.kind or "other"] = counts.get(change.kind or "other", 0) + 1
    if args.kinds:
        changes = [c for c in changes if c.kind in args.kinds]
    changes.sort(key=lambda c: c.date or "", reverse=True)
    items = [
        ChangeOut(package_id=c.package.package_id, kind=c.kind, date=c.date, doi=c.doi)
        for c in changes
    ]
    page_items, page = paginate(items, offset=args.offset, limit=args.limit)
    steps = [f"edi_get_package(package='{c.package_id}')" for c in page_items[:2]]
    if page.next_offset is not None:
        steps.append(f"edi_recent_changes(..., offset={page.next_offset})")
    return ChangesResult(
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        scope=scope,
        changes=page_items,
        counts=counts,
        page=page,
        resolved=echoes,
        notes=merge_notes(backend.notes),
        next_steps=steps,
        source=source(ctx),
    )


# ---------------------------------------------------------------------------
# edi_get_read_counts
# ---------------------------------------------------------------------------


class ReadsIn(EdiInput):
    package: str = Field(
        min_length=1,
        max_length=500,
        description="A series (knb-lter-hbr.14) for every revision, or one revision "
        "(knb-lter-hbr.14.22); the scope may be a site code or name.",
    )
    revision: int | None = Field(None, ge=0, description="Only this revision of a series.")


class ReadTally(EdiOutput):
    total: int = 0
    non_robot: int = Field(0, description="Reads not attributed to robots.")


class RevisionReads(EdiOutput):
    revision: int
    package: ReadTally = Field(description="Reads of the package itself.")
    data: ReadTally = Field(description="Reads of its data entities.")


class ReadsResult(ToolResultBase):
    series: str
    revision: int | None = None
    totals: dict[str, ReadTally] = Field(
        description="By resource type: dataPackage, metadata, report, data, archive."
    )
    revisions: list[RevisionReads] = Field(description="Newest first (at most 100).")
    revisions_total: int


def _tally(rows: list[ResourceReads], kind: Literal["package", "data"]) -> ReadTally:
    wanted = {"dataPackage"} if kind == "package" else {"data"}
    picked = [r for r in rows if r.resource_type in wanted]
    return ReadTally(total=sum(r.total for r in picked), non_robot=sum(r.non_robot for r in picked))


@register_tool(
    "edi_get_read_counts",
    title="Get a package's read counts",
    description=(
        "How often a package series or one revision has been read on PASTA: totals and "
        "non-robot reads by resource type (package, metadata, quality report, data entities, "
        "zip archive) and per revision. Needs an EDI API key. Next: cite the package with "
        "edi_get_citation."
    ),
    input_model=ReadsIn,
    output_model=ReadsResult,
    surface="feeds",
    endpoints=["GET pasta.lternet.edu/audit/reads/{scope}/{id}[/{rev}]"],
    requires_key=True,
)
async def edi_get_read_counts(args: ReadsIn, ctx: ToolContext) -> ReadsResult:
    backend = _pasta(ctx)
    ref, echoes = resolve_reference(args.package, args.revision)
    if ref.doi is not None:
        package = await backend.resolve_doi(ref.doi)
        scope, identifier, revision = package.scope, package.identifier, package.revision
    elif ref.package is not None:
        scope, identifier = ref.package.scope, ref.package.identifier
        revision = ref.revision if isinstance(ref.revision, int) else None
    else:  # pragma: no cover - resolve_reference returns a package or a DOI
        raise ToolError("invalid_argument", f"{args.package!r} names no package.")
    rows = await backend.read_counts(scope, identifier, revision)
    totals: dict[str, ReadTally] = {}
    for row in rows:
        tally = totals.setdefault(row.resource_type, ReadTally())
        tally.total += row.total
        tally.non_robot += row.non_robot
    by_revision: dict[int, list[ResourceReads]] = {}
    for row in rows:
        if row.revision is not None:
            by_revision.setdefault(row.revision, []).append(row)
    revisions = [
        RevisionReads(revision=rev, package=_tally(items, "package"), data=_tally(items, "data"))
        for rev, items in sorted(by_revision.items(), reverse=True)
    ]
    series = f"{scope}.{identifier}"
    notes = []
    if not rows:
        notes.append("PASTA recorded no reads for this package.")
    if len(revisions) > MAX_REVISIONS:
        notes.append(f"Showing the newest {MAX_REVISIONS} of {len(revisions)} revisions.")
    return ReadsResult(
        series=series,
        revision=revision,
        totals=totals,
        revisions=revisions[:MAX_REVISIONS],
        revisions_total=len(revisions),
        resolved=echoes,
        notes=merge_notes(backend.notes, notes),
        next_steps=[
            f"edi_get_citation(package='{series}{'.' + str(revision) if revision is not None else ''}')"
        ],
        source=source(ctx, derived=["totals", "revisions"]),
    )
