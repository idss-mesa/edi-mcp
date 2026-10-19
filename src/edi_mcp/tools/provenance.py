"""Provenance tools: ``edi_get_quality_report`` and ``edi_get_lineage``.

Quality reports are PASTA's congruence checks, replicated to the DataONE member
nodes and served there without a key (verified 2026-10-19, RESEARCH.md section 7),
so the tool works on both backends. Lineage (``/sources``, ``/descendants``) is
PASTA-only.
"""

from __future__ import annotations

from pydantic import Field

from edi_mcp.context import ToolContext
from edi_mcp.edi.backends import PastaBackend, backend_for, resolve_package
from edi_mcp.edi.backends.pasta import LinkedPackage
from edi_mcp.edi.xml import parse_xml
from edi_mcp.errors import ToolError
from edi_mcp.models.common import EdiOutput, Resolved, ToolResultBase
from edi_mcp.projections.report import (
    MAX_ISSUES,
    EntityQuality,
    QualityIssue,
    StatusCounts,
    project_report,
)
from edi_mcp.registry import register_tool
from edi_mcp.tools._common import merge_notes, source
from edi_mcp.tools.data import require_replicated
from edi_mcp.tools.packages import PackageArgs, RevisionFrom


def _echo(resolved_raw: str, package_id: str, given: str, extra: list[Resolved]) -> list[Resolved]:
    out = list(extra)
    if resolved_raw.strip() != package_id:
        out.append(Resolved(field="package", input=given, code=package_id, confidence=1.0))
    return out


# ---------------------------------------------------------------------------
# edi_get_quality_report
# ---------------------------------------------------------------------------


class QualityIn(PackageArgs):
    include_info: bool = Field(False, description="Also list 'info' checks, not only warn/error.")


class QualityResult(ToolResultBase):
    package_id: str
    revision_from: RevisionFrom
    created: str | None = None
    counts: StatusCounts = Field(description="Checks by status, dataset and entities together.")
    issues: list[QualityIssue] = Field(description="Non-valid checks, errors first.")
    issues_total: int
    entities: list[EntityQuality]
    entities_total: int


@register_tool(
    "edi_get_quality_report",
    title="Get a package's quality report",
    description=(
        "PASTA's quality report for one package revision: how many congruence checks passed, "
        "warned or failed (metadata, and each data entity against its EML), and the details of "
        "every non-valid check with EDI's explanation and suggestion. Works with a key (PASTA) "
        "or without (DataONE member node). Next: inspect a flagged entity with "
        "edi_list_entities or edi_preview_entity."
    ),
    input_model=QualityIn,
    output_model=QualityResult,
    surface="provenance",
    endpoints=[
        "GET pasta.lternet.edu/package/report/eml/{scope}/{id}/{rev}",
        "GET gmn.lternet.edu/mn/v2/object/{pid}",
    ],
)
async def edi_get_quality_report(args: QualityIn, ctx: ToolContext) -> QualityResult:
    backend = backend_for(ctx)
    if backend.name == "dataone":
        require_replicated(args, ctx)
    resolved = await resolve_package(backend, args.package, args.revision)
    package = resolved.package
    body = await backend.read_report(package)
    root = parse_xml(
        body,
        source=backend.report_pid(package),
        service="PASTA" if backend.name == "pasta" else "DataONE",
    )
    report = project_report(root, include_info=args.include_info)
    notes = []
    if report.issues_total > len(report.issues):
        notes.append(
            f"Showing {len(report.issues)} of {report.issues_total} issues (cap {MAX_ISSUES})."
        )
    if report.counts.error == 0 and report.counts.warn == 0:
        notes.append("Every check passed or is informational.")
    return QualityResult(
        package_id=package.package_id,
        revision_from=resolved.revision_from,
        created=report.created,
        counts=report.counts,
        issues=report.issues,
        issues_total=report.issues_total,
        entities=report.entities,
        entities_total=report.entities_total,
        resolved=_echo(resolved.raw, package.package_id, args.package, resolved.resolved),
        notes=merge_notes(backend.notes, notes),
        next_steps=[f"edi_list_entities(package='{package.package_id}')"],
        source=source(ctx, derived=["counts", "issues"]),
    )


# ---------------------------------------------------------------------------
# edi_get_lineage
# ---------------------------------------------------------------------------


class LineageIn(PackageArgs):
    pass


class LinkedOut(EdiOutput):
    package_id: str | None = None
    title: str | None = None
    url: str | None = None


class LineageResult(ToolResultBase):
    package_id: str
    revision_from: RevisionFrom
    sources: list[LinkedOut] = Field(description="Packages this one was derived from.")
    descendants: list[LinkedOut] = Field(description="Packages derived from this one.")


def _linked(items: list[LinkedPackage]) -> list[LinkedOut]:
    return [
        LinkedOut(package_id=i.package.package_id if i.package else None, title=i.title, url=i.url)
        for i in items
    ]


@register_tool(
    "edi_get_lineage",
    title="Get a package's provenance",
    description=(
        "Provenance of one package revision: the EDI packages it was derived from (sources "
        "named in its EML methods) and the packages that name it as a source (descendants), "
        "with titles. Needs an EDI API key. Next: call edi_get_package on a source or "
        "descendant."
    ),
    input_model=LineageIn,
    output_model=LineageResult,
    surface="provenance",
    endpoints=[
        "GET pasta.lternet.edu/package/sources/eml/{scope}/{id}/{rev}",
        "GET pasta.lternet.edu/package/descendants/eml/{scope}/{id}/{rev}",
    ],
    requires_key=True,
)
async def edi_get_lineage(args: LineageIn, ctx: ToolContext) -> LineageResult:
    backend = backend_for(ctx)
    if not isinstance(backend, PastaBackend):  # pragma: no cover - the registry requires a key
        raise ToolError("auth_required", "Lineage needs an EDI API key.")
    resolved = await resolve_package(backend, args.package, args.revision)
    package = resolved.package
    sources = _linked(await backend.data_sources(package))
    descendants = _linked(await backend.data_descendants(package))
    steps = [
        f"edi_get_package(package='{item.package_id}')"
        for item in (sources + descendants)[:3]
        if item.package_id
    ]
    notes = []
    if not sources and not descendants:
        notes.append("PASTA records no source or descendant packages for this revision.")
    return LineageResult(
        package_id=package.package_id,
        revision_from=resolved.revision_from,
        sources=sources,
        descendants=descendants,
        resolved=_echo(resolved.raw, package.package_id, args.package, resolved.resolved),
        notes=merge_notes(backend.notes, notes),
        next_steps=steps,
        source=source(ctx),
    )
