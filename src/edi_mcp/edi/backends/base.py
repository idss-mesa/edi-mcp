"""The backend contract both upstream routes implement (DESIGN.md D1).

:class:`PastaBackend` serves a call that has an EDI API key;
:class:`DataOneBackend` serves one without. Both return the same plain
dataclasses, so tools never branch on the backend; each records what it
called in the call's :class:`UpstreamStats` and adds caveats to ``notes``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

from edi_mcp.edi.pid import Doi, PackageId, RevisionSpec, parse_reference
from edi_mcp.errors import EdiApiError, ToolError, map_api_error
from edi_mcp.logging import registered_secrets

if TYPE_CHECKING:
    from edi_mcp.config import Config
    from edi_mcp.context import UpstreamStats
    from edi_mcp.edi.client import EdiClient

BackendName = Literal["pasta", "dataone"]

#: DataONE identifiers of PASTA content always use the production host.
PASTA_PID_BASE = "https://pasta.lternet.edu/package"
#: Bulk scopes that swamp keyword search (~26k records); excluded unless asked for.
BULK_SCOPES = ("ecotrends", "lter-landsat")


@dataclass(frozen=True)
class SearchQuery:
    text: str | None = None
    scope: str | None = None
    offset: int = 0
    limit: int = 10
    exclude_bulk: bool = True


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


class Backend(Protocol):
    name: BackendName
    notes: list[str]

    async def search(self, query: SearchQuery) -> SearchPage: ...
    async def list_identifiers(self, scope: str) -> list[int]: ...
    async def list_revisions(self, scope: str, identifier: int) -> list[int]: ...
    async def read_eml(self, package: PackageId) -> bytes: ...
    async def list_entities(self, package: PackageId) -> list[EntityInfo]: ...
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
    ref = parse_reference(value, revision)
    if ref.doi is not None:
        package = await backend.resolve_doi(ref.doi)
        if isinstance(revision, int) and package.revision != revision:
            raise ToolError(
                "invalid_argument",
                f"{ref.doi.pid} is revision {package.revision} of {package.series}, not {revision}.",
                details={"doi": ref.doi.pid, "packageId": str(package)},
                hint="A DOI names exactly one revision; omit revision.",
            )
        return ResolvedPackage(package, ref.raw, ref.form, ref.entity_id, "doi")
    if ref.package is None:  # pragma: no cover - parse_reference returns a package or a DOI
        raise ToolError("invalid_argument", f"{value!r} names no package.")
    if isinstance(ref.revision, int):
        return ResolvedPackage(ref.package, ref.raw, ref.form, ref.entity_id, "given")
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
        ref.package.with_revision(chosen), ref.raw, ref.form, ref.entity_id, which
    )


__all__ = [
    "BULK_SCOPES",
    "PASTA_PID_BASE",
    "Backend",
    "BackendBase",
    "BackendName",
    "EntityInfo",
    "ResolvedPackage",
    "SearchHit",
    "SearchPage",
    "SearchQuery",
    "pick_revision",
    "resolve_package",
]
