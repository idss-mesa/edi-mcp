"""Project a PASTA quality report (``qr:qualityReport``) into a compact summary.

A report holds one ``qualityCheck`` per dataset-level test plus an
``entityReport`` per data entity; each check has a ``status`` of valid, info,
warn or error. Most checks are valid, so the projection keeps counts for all
and details only for the others, capped with a total.
"""

from __future__ import annotations

from typing import Literal
from xml.etree.ElementTree import Element

from pydantic import Field

from edi_mcp.edi.xml import children, descendants, text_of
from edi_mcp.models.common import EdiOutput
from edi_mcp.projections.eml import cut

Status = Literal["valid", "info", "warn", "error"]
STATUSES: tuple[Status, ...] = ("valid", "info", "warn", "error")
MAX_ISSUES = 50
MAX_ENTITIES = 50
FOUND_CHARS = 200
TEXT_CHARS = 300


class StatusCounts(EdiOutput):
    valid: int = 0
    info: int = 0
    warn: int = 0
    error: int = 0


class QualityIssue(EdiOutput):
    entity: str | None = Field(None, description="Entity name; null for dataset-level checks.")
    status: Status
    identifier: str | None = None
    name: str | None = None
    found: str | None = None
    explanation: str | None = None
    suggestion: str | None = None


class EntityQuality(EdiOutput):
    name: str | None = None
    counts: StatusCounts


class ReportProjection(EdiOutput):
    package_id: str | None = None
    created: str | None = None
    counts: StatusCounts
    issues: list[QualityIssue]
    issues_total: int
    entities: list[EntityQuality]
    entities_total: int


def _status(check: Element) -> Status | None:
    value = (text_of(check, "status") or "").strip().lower()
    return value if value in STATUSES else None


def project_report(root: Element, *, include_info: bool = False) -> ReportProjection:
    totals = StatusCounts()
    issues: list[QualityIssue] = []
    issues_total = 0
    wanted: set[str] = {"warn", "error"} | ({"info"} if include_info else set())

    def tally(check: Element, counts: StatusCounts, entity: str | None) -> None:
        nonlocal issues_total
        status = _status(check)
        if status is None:
            return
        for target in (counts, totals) if counts is not totals else (totals,):
            setattr(target, status, getattr(target, status) + 1)
        if status not in wanted:
            return
        issues_total += 1
        if len(issues) < MAX_ISSUES:
            issues.append(
                QualityIssue(
                    entity=entity,
                    status=status,
                    identifier=text_of(check, "identifier"),
                    name=text_of(check, "name"),
                    found=cut(text_of(check, "found"), FOUND_CHARS)[0],
                    explanation=cut(text_of(check, "explanation"), TEXT_CHARS)[0],
                    suggestion=cut(text_of(check, "suggestion"), TEXT_CHARS)[0],
                )
            )

    for report in children(root, "datasetReport"):
        for check in children(report, "qualityCheck"):
            tally(check, totals, None)
    entities: list[EntityQuality] = []
    reports = list(children(root, "entityReport"))
    for report in reports:
        name = text_of(report, "entityName") or text_of(report, "entityId")
        counts = StatusCounts()
        for check in descendants(report, "qualityCheck"):
            tally(check, counts, name)
        if len(entities) < MAX_ENTITIES:
            entities.append(EntityQuality(name=name, counts=counts))
    # Errors first, then warnings, then info.
    order = {"error": 0, "warn": 1, "info": 2, "valid": 3}
    issues.sort(key=lambda i: order[i.status])
    return ReportProjection(
        package_id=text_of(root, "packageId"),
        created=text_of(root, "creationDate"),
        counts=totals,
        issues=issues,
        issues_total=issues_total,
        entities=entities,
        entities_total=len(reports),
    )


__all__ = [
    "MAX_ENTITIES",
    "MAX_ISSUES",
    "EntityQuality",
    "QualityIssue",
    "ReportProjection",
    "StatusCounts",
    "project_report",
]
