"""The backend contract both upstream routes implement (DESIGN.md D1).

:class:`PastaBackend` serves a call that has an EDI API key;
:class:`DataOneBackend` serves one without. Both return the same plain
dataclasses, so tools never branch on the backend; each records what it
called in the call's :class:`UpstreamStats` and adds caveats to ``notes``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol
from urllib.parse import quote

from edi_mcp.edi.eml import EmlEntity
from edi_mcp.edi.pid import Doi, PackageId, RevisionSpec
from edi_mcp.edi.scopes import resolve_reference
from edi_mcp.errors import EdiApiError, ToolError, map_api_error
from edi_mcp.logging import registered_secrets
from edi_mcp.models.common import Resolved

if TYPE_CHECKING:
    from edi_mcp.config import Config
    from edi_mcp.context import UpstreamStats
    from edi_mcp.edi.client import EdiClient

BackendName = Literal["pasta", "dataone"]

#: DataONE identifiers of PASTA content always use the production host.
PASTA_PID_BASE = "https://pasta.lternet.edu/package"
#: Bulk scopes that swamp search (~36k generated records); excluded unless asked for.
BULK_SCOPES = ("ecotrends", "lter-landsat", "lter-landsat-ledaps")

SearchSort = Literal["relevance", "newest", "oldest"]
_LOCAL_PARAMS = re.compile(r"^\s*(?:\{![^}]*\}\s*)+")


@dataclass(frozen=True)
class BoundingBox:
    """West, south, east, north in decimal degrees (``west <= east``: no antimeridian)."""

    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True)
class SearchQuery:
    text: str | None = None
    scope: str | None = None
    offset: int = 0
    limit: int = 10
    exclude_bulk: bool = True
    #: A creator's last name (case-insensitive on both backends).
    author: str | None = None
    #: Temporal coverage overlapping [start_year, end_year] (either end optional).
    start_year: int | None = None
    end_year: int | None = None
    bbox: BoundingBox | None = None
    sort: SearchSort = "relevance"

    @property
    def query_text(self) -> str:
        """The free text for ``q``; a leading ``{!...}`` local-params block (which could
        switch Solr's query parser) is dropped."""
        text = _LOCAL_PARAMS.sub("", self.text or "").strip()
        return text or "*:*"


def solr_phrase(value: str) -> str:
    """``value`` as a quoted Solr phrase: only backslash and quote are special inside."""
    cleaned = " ".join(value.replace("\\", " ").replace('"', " ").split())
    return f'"{cleaned}"'


def year_start(year: int) -> str:
    return f"{year:04d}-01-01T00:00:00Z"


def year_end(year: int) -> str:
    return f"{year:04d}-12-31T23:59:59Z"


@dataclass
class SearchHit:
    package: PackageId
    title: str | None = None
    pub_date: str | None = None
    doi: str | None = None
    begin_date: str | None = None
    end_date: str | None = None
    keywords: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    #: DataONE only: when this revision was uploaded (its sort key for newest/oldest).
    uploaded: str | None = None


@dataclass
class SearchPage:
    hits: list[SearchHit]
    total: int | None
    total_exact: bool
    offset: int
    limit: int


@dataclass
class EntityInfo:
    entity_id: str
    name: str | None
    size: int | None = None
    sha1: str | None = None
    format_id: str | None = None
    object_name: str | None = None
    entity_type: str | None = None
    #: The canonical PASTA data URL (also the entity's DataONE identifier).
    url: str = ""


@dataclass
class ResolvedPackage:
    package: PackageId
    raw: str
    form: str
    entity_id: str | None
    #: How the revision was chosen: given, newest, oldest, or via the DOI.
    revision_from: Literal["given", "newest", "oldest", "doi"]
    #: Scope names or site codes resolved to a scope (D9), for the result's ``resolved``.
    resolved: list[Resolved] = field(default_factory=list)


class Backend(Protocol):
    notes: list[str]

    @property
    def name(self) -> BackendName: ...

    async def search(self, query: SearchQuery) -> SearchPage: ...
    async def list_identifiers(self, scope: str) -> list[int]: ...
    async def list_revisions(self, scope: str, identifier: int) -> list[int]: ...
    async def read_eml(self, package: PackageId) -> bytes: ...
    async def list_entities(
        self, package: PackageId, refs: list[EmlEntity] | None = None
    ) -> list[EntityInfo]: ...
    async def entity_checksum(self, package: PackageId, entity_id: str) -> str | None: ...
    async def package_doi(self, package: PackageId) -> str | None: ...
    async def resolve_doi(self, doi: Doi) -> PackageId: ...
    def data_url(self, package: PackageId, entity_id: str) -> str: ...


class BackendBase:
    name: BackendName

    def __init__(self, client: EdiClient, config: Config, stats: UpstreamStats) -> None:
        self.client = client
        self.config = config
        self.stats = stats
        self.notes: list[str] = []
        if stats.backend is None:
            stats.backend = self.name

    def note(self, text: str) -> None:
        if text not in self.notes:
            self.notes.append(text)

    def data_url(self, package: PackageId, entity_id: str) -> str:
        return f"{PASTA_PID_BASE}/data/eml/{package.path}/{entity_id}"

    def member_node(self, scope: str) -> str:
        """The DataONE member node holding ``scope`` (``…/mn/v2``, no trailing slash)."""
        edi = self.config.edi
        return (edi.gmn_edi_url if scope == "edi" else edi.gmn_lter_url).rstrip("/")

    def anonymous_data_url(self, package: PackageId, entity_id: str) -> str:
        """The entity on its DataONE member node, readable without a key (GMN proxies PASTA)."""
        return f"{self.member_node(package.scope)}/object/{quote(self.data_url(package, entity_id), safe='')}"

    def metadata_pid(self, package: PackageId) -> str:
        return f"{PASTA_PID_BASE}/metadata/eml/{package.path}"

    def not_found_hint(self) -> str | None:
        return None

    def not_found(self, exc: EdiApiError, entity: str, identifier: str) -> ToolError:
        err = map_api_error(exc, entity=entity, identifier=identifier, secrets=registered_secrets())
        hint = self.not_found_hint()
        if err.code == "not_found" and hint:
            err.hint = hint
        return err


def pick_revision(revisions: list[int], which: Literal["newest", "oldest"]) -> int | None:
    if not revisions:
        return None
    return max(revisions) if which == "newest" else min(revisions)


async def resolve_package(
    backend: Backend, value: str, revision: RevisionSpec = None
) -> ResolvedPackage:
    """Parse ``value`` and fill in a concrete revision (DOI lookup or revision listing)."""
    ref, resolved = resolve_reference(value, revision)
    if ref.doi is not None:
        package = await backend.resolve_doi(ref.doi)
        if isinstance(revision, int) and package.revision != revision:
            raise ToolError(
                "invalid_argument",
                f"{ref.doi.pid} is revision {package.revision} of {package.series}, not {revision}.",
                details={"doi": ref.doi.pid, "packageId": str(package)},
                hint="A DOI names exactly one revision; omit revision.",
            )
        return ResolvedPackage(package, ref.raw, ref.form, ref.entity_id, "doi", resolved)
    if ref.package is None:  # pragma: no cover - parse_reference returns a package or a DOI
        raise ToolError("invalid_argument", f"{value!r} names no package.")
    if isinstance(ref.revision, int):
        return ResolvedPackage(ref.package, ref.raw, ref.form, ref.entity_id, "given", resolved)
    which: Literal["newest", "oldest"] = "oldest" if ref.revision == "oldest" else "newest"
    revisions = await backend.list_revisions(ref.package.scope, ref.package.identifier)
    chosen = pick_revision(revisions, which)
    if chosen is None:
        raise ToolError(
            "not_found",
            f"No revisions of {ref.package.series} were found.",
            details={"identifier": ref.package.series, "backend": backend.name},
            hint=(
                "Check the scope and identifier with edi_search_packages."
                if backend.name == "pasta"
                else "DataONE can lag EDI; set EDI_API_KEY to read PASTA directly."
            ),
        )
    return ResolvedPackage(
        ref.package.with_revision(chosen), ref.raw, ref.form, ref.entity_id, which, resolved
    )


__all__ = [
    "BULK_SCOPES",
    "PASTA_PID_BASE",
    "Backend",
    "BackendBase",
    "BackendName",
    "BoundingBox",
    "EntityInfo",
    "ResolvedPackage",
    "SearchHit",
    "SearchPage",
    "SearchQuery",
    "SearchSort",
    "pick_revision",
    "resolve_package",
    "solr_phrase",
    "year_end",
    "year_start",
]
