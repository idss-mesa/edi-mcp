"""PASTA+ backend: used when the call has an EDI API key (DESIGN.md D1).

Every request goes to ``{pasta_base_url}/package/…`` with the call's key,
which the client turns into an ``edi-token`` cookie (D4). Response formats
were verified on 2026-10-17 (RESEARCH.md section 1): listings are
newline-separated text, entity names and sizes are ``id,value`` CSV, search
is Solr XML (``<resultset numFound>``).
"""

from __future__ import annotations

import html
import re
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from edi_mcp.edi.backends.base import (
    BULK_SCOPES,
    BackendBase,
    EntityInfo,
    SearchHit,
    SearchPage,
    SearchQuery,
    solr_phrase,
    year_end,
    year_start,
)
from edi_mcp.edi.pid import Doi, PackageId, parse_reference
from edi_mcp.edi.xml import children, descendants, parse_xml, text_of
from edi_mcp.errors import EdiApiError, ToolError

if TYPE_CHECKING:
    from edi_mcp.config import Config
    from edi_mcp.context import UpstreamStats
    from edi_mcp.edi.auth import ApiKey
    from edi_mcp.edi.backends.dataone import DataOneBackend
    from edi_mcp.edi.cache import CacheFamily
    from edi_mcp.edi.client import EdiClient, Fetched, Streamed
    from edi_mcp.edi.eml import EmlEntity

SEARCH_FIELDS = "packageid,title,pubdate,doi,begindate,enddate,scope,keyword,author"
ChangeKind = Literal["insert", "update", "delete"]
_METHOD_KIND: dict[str, ChangeKind] = {
    "createdatapackage": "insert",
    "updatedatapackage": "update",
    "deletedatapackage": "delete",
}
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})")


@dataclass
class LinkedPackage:
    """One provenance source or descendant (``/sources``, ``/descendants``)."""

    package: PackageId | None
    title: str | None
    url: str | None


@dataclass
class PackageChange:
    """One entry of ``/changes/eml`` (the uploader's principal is never kept)."""

    package: PackageId
    kind: ChangeKind | None
    method: str | None
    date: str | None
    doi: str | None


@dataclass
class ResourceReads:
    """One ``/audit/reads`` resource: total and non-robot reads."""

    resource_type: str
    revision: int | None
    entity_id: str | None
    total: int
    non_robot: int


def _iso(value: str | None) -> str | None:
    """``2026-10-12T22:19:37.455`` and ``2026-10-19 17:53:59`` → ``2026-10-12T22:19:37Z``
    (PASTA reports UTC)."""
    m = _DATE_RE.match((value or "").strip())
    return f"{m.group(1)}T{m.group(2)}Z" if m else None


def _int(value: str | None) -> int:
    text = (value or "").strip()
    return int(text) if text.isdigit() else 0


def _title(value: str | None) -> str | None:
    """Lineage titles arrive escaped twice (``&#x3a;`` survives XML parsing)."""
    if not value:
        return None
    return " ".join(html.unescape(value).split()) or None


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _ints(text: str) -> list[int]:
    return sorted({int(line) for line in _lines(text) if line.isdigit()})


def _csv_pairs(text: str) -> list[tuple[str, str]]:
    """``id,value`` lines; the value may itself contain commas (entity names)."""
    out = []
    for line in _lines(text):
        entity_id, _, value = line.partition(",")
        out.append((entity_id.strip(), value.strip()))
    return out


def search_filter(query: SearchQuery) -> str | None:
    """One ``fq`` for PASTA's Solr: positive clauses first, the bulk exclusion last."""
    clauses: list[str] = []
    if query.scope:
        clauses.append(f"scope:{query.scope}")
    if query.author:
        clauses.append(f"author:{solr_phrase(query.author)}")
    if query.end_year is not None:
        clauses.append(f"begindate:[* TO {year_end(query.end_year)}]")
    if query.start_year is not None:
        clauses.append(f"enddate:[{year_start(query.start_year)} TO *]")
    if query.bbox is not None:
        b = query.bbox
        # Solr's ENVELOPE takes minX, maxX, maxY, minY.
        clauses.append(
            f'coordinates:"Intersects(ENVELOPE({b.west}, {b.east}, {b.north}, {b.south}))"'
        )
    if not query.scope and query.exclude_bulk:
        clauses.append(f"-scope:({' '.join(BULK_SCOPES)})")
    return " AND ".join(clauses) or None


class PastaBackend(BackendBase):
    name = "pasta"

    def __init__(
        self,
        client: EdiClient,
        config: Config,
        stats: UpstreamStats,
        key: ApiKey,
    ) -> None:
        super().__init__(client, config, stats)
        self.key = key
        self.base = config.edi.pasta_base_url.rstrip("/") + "/package"
        self._fallback: DataOneBackend | None = None

    def set_fallback(self, fallback: DataOneBackend) -> None:
        """DataONE answers what PASTA search cannot: DOIs of superseded revisions."""
        self._fallback = fallback

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
        *,
        cache: CacheFamily | None,
        max_bytes: int | None = None,
    ) -> Fetched:
        return await self.client.get(
            f"{self.base}{path}",
            params,
            key=self.key,
            cache=cache,
            stats=self.stats,
            max_bytes=max_bytes,
        )

    # ------------------------------------------------------------------ search

    async def _search_xml(self, params: dict[str, str]) -> tuple[int | None, list[SearchHit]]:
        fetched = await self._get("/search/eml", params, cache="search")
        root = parse_xml(fetched.body, source="/package/search/eml")
        found = root.get("numFound")
        hits: list[SearchHit] = []
        for doc in children(root, "document"):
            packageid = text_of(doc, "packageid")
            if not packageid:
                continue
            ref = parse_reference(packageid)
            if ref.package is None or ref.package.revision is None:
                continue
            hits.append(
                SearchHit(
                    package=ref.package,
                    title=text_of(doc, "title"),
                    pub_date=text_of(doc, "pubdate"),
                    doi=text_of(doc, "doi"),
                    begin_date=text_of(doc, "begindate"),
                    end_date=text_of(doc, "enddate"),
                    keywords=[k.text.strip() for k in descendants(doc, "keyword") if k.text],
                    authors=[a.text.strip() for a in descendants(doc, "author") if a.text],
                )
            )
        return (int(found) if found and found.isdigit() else None), hits

    async def search(self, query: SearchQuery) -> SearchPage:
        params = {
            "defType": "edismax",
            "q": query.query_text,
            "fl": SEARCH_FIELDS,
            "rows": str(query.limit),
            "start": str(query.offset),
        }
        fq = search_filter(query)
        if fq:
            params["fq"] = fq
        if query.sort != "relevance":
            # PASTA wants "field,direction"; "pubdate desc" is accepted and ignored.
            params["sort"] = "pubdate,desc" if query.sort == "newest" else "pubdate,asc"
        total, hits = await self._search_xml(params)
        self.note("PASTA search covers the newest revision of each package only.")
        return SearchPage(hits, total, True, query.offset, query.limit)

    # ------------------------------------------------------------------ listings

    async def list_scopes(self) -> list[str]:
        """PASTA-only: every scope in the repository."""
        return _lines((await self._get("/eml", cache="listings")).text)

    async def list_identifiers(self, scope: str) -> list[int]:
        try:
            fetched = await self._get(f"/eml/{scope}", cache="listings")
        except EdiApiError as exc:
            raise self.not_found(exc, "scope", scope) from None
        return _ints(fetched.text)

    async def list_revisions(self, scope: str, identifier: int) -> list[int]:
        try:
            fetched = await self._get(f"/eml/{scope}/{identifier}", cache="listings")
        except EdiApiError as exc:
            if exc.status == 404:
                return []
            raise
        return _ints(fetched.text)

    # ------------------------------------------------------------------ package

    async def read_eml(self, package: PackageId) -> bytes:
        try:
            fetched = await self._get(
                f"/metadata/eml/{package.path}",
                cache="metadata",
                max_bytes=self.config.limits.max_eml_bytes,
            )
        except EdiApiError as exc:
            raise self.not_found(exc, "package", str(package)) from None
        return fetched.body

    async def list_entities(
        self, package: PackageId, refs: list[EmlEntity] | None = None
    ) -> list[EntityInfo]:
        """PASTA's authoritative names and byte sizes (``refs`` is unused here)."""
        del refs
        try:
            names = _csv_pairs(
                (await self._get(f"/name/eml/{package.path}", cache="metadata")).text
            )
        except EdiApiError as exc:
            raise self.not_found(exc, "package", str(package)) from None
        sizes = dict(
            _csv_pairs((await self._get(f"/data/size/eml/{package.path}", cache="metadata")).text)
        )
        out = []
        for entity_id, name in names:
            size = sizes.get(entity_id, "")
            out.append(
                EntityInfo(
                    entity_id=entity_id,
                    name=name or None,
                    size=int(size) if size.isdigit() else None,
                    url=self.data_url(package, entity_id),
                )
            )
        return out

    async def entity_checksum(self, package: PackageId, entity_id: str) -> str | None:
        try:
            fetched = await self._get(
                f"/data/checksum/eml/{package.path}/{entity_id}", cache="metadata"
            )
        except EdiApiError as exc:
            raise self.not_found(exc, "entity", f"{package}/{entity_id}") from None
        value = fetched.text.strip().lower()
        return value or None

    async def package_doi(self, package: PackageId) -> str | None:
        try:
            fetched = await self._get(f"/doi/eml/{package.path}", cache="metadata")
        except EdiApiError as exc:
            raise self.not_found(exc, "package", str(package)) from None
        value = fetched.text.strip()
        return value or None

    async def read_report(self, package: PackageId) -> bytes:
        try:
            fetched = await self._get(
                f"/report/eml/{package.path}",
                cache="reports",
                max_bytes=self.config.limits.max_eml_bytes,
            )
        except EdiApiError as exc:
            raise self.not_found(exc, "quality report", str(package)) from None
        return fetched.body

    # ------------------------------------------------------------------ PASTA only

    async def _linked(
        self, kind: Literal["sources", "descendants"], package: PackageId
    ) -> list[LinkedPackage]:
        try:
            fetched = await self._get(f"/{kind}/eml/{package.path}", cache="reports")
        except EdiApiError as exc:
            raise self.not_found(exc, "package", str(package)) from None
        root = parse_xml(fetched.body, source=f"/package/{kind}/eml")
        out = []
        tag = "dataSource" if kind == "sources" else "dataDescendant"
        for item in descendants(root, tag):
            pid = text_of(item, "packageId")
            ref = None
            if pid:
                try:
                    ref = parse_reference(pid).package
                except ToolError:
                    ref = None
            out.append(LinkedPackage(ref, _title(text_of(item, "title")), text_of(item, "url")))
        return out

    async def data_sources(self, package: PackageId) -> list[LinkedPackage]:
        """Packages this one was derived from (EML ``methods/dataSource``)."""
        return await self._linked("sources", package)

    async def data_descendants(self, package: PackageId) -> list[LinkedPackage]:
        """Packages that name this one as a source."""
        return await self._linked("descendants", package)

    async def changes(
        self, from_date: str, to_date: str | None, scope: str | None
    ) -> list[PackageChange]:
        """Inserts, updates and deletes between two dates (``/changes/eml``)."""
        params = {"fromDate": from_date, "toDate": to_date, "scope": scope}
        fetched = await self._get(
            "/changes/eml", {k: v for k, v in params.items() if v}, cache="feeds"
        )
        root = parse_xml(fetched.body, source="/package/changes/eml")
        out = []
        for item in descendants(root, "dataPackage"):
            pid = text_of(item, "packageId")
            try:
                ref = parse_reference(pid or "").package
            except ToolError:
                ref = None
            if ref is None or ref.revision is None:
                continue
            method = text_of(item, "serviceMethod")
            out.append(
                PackageChange(
                    package=ref,
                    kind=_METHOD_KIND.get((method or "").lower()),
                    method=method,
                    date=_iso(text_of(item, "date")),
                    doi=text_of(item, "doi") or None,
                )
            )
        return out

    async def read_counts(
        self, scope: str, identifier: int, revision: int | None
    ) -> list[ResourceReads]:
        """``/audit/reads/{scope}/{id}[/{rev}]``: reads per resource (package, metadata,
        report, each data entity)."""
        path = f"{scope}/{identifier}" + (f"/{revision}" if revision is not None else "")
        try:
            fetched = await self.client.get(
                f"{self.config.edi.pasta_base_url.rstrip('/')}/audit/reads/{path}",
                key=self.key,
                cache="feeds",
                stats=self.stats,
            )
        except EdiApiError as exc:
            raise self.not_found(exc, "package", path.replace("/", ".")) from None
        root = parse_xml(fetched.body, source="/audit/reads")
        out = []
        for item in descendants(root, "resource"):
            resource_id = text_of(item, "resourceId") or ""
            entity = None
            if (text_of(item, "resourceType") or "") == "data":
                entity = resource_id.rstrip("/").rsplit("/", 1)[-1] or None
            rev = text_of(item, "revision")
            out.append(
                ResourceReads(
                    resource_type=text_of(item, "resourceType") or "unknown",
                    revision=int(rev) if rev and rev.isdigit() else None,
                    entity_id=entity,
                    total=_int(text_of(item, "totalReads")),
                    non_robot=_int(text_of(item, "nonRobotReads")),
                )
            )
        return out

    def stream_package_zip(
        self,
        package: PackageId,
        *,
        allowed_hosts: list[str] | None = None,
        read_timeout_s: float | None = None,
    ) -> AbstractAsyncContextManager[Streamed]:
        """The whole package as one zip (``/download/eml``), streamed."""
        return self.client.stream(
            f"{self.base}/download/eml/{package.path}",
            key=self.key,
            stats=self.stats,
            allowed_hosts=allowed_hosts,
            read_timeout_s=read_timeout_s,
        )

    async def resolve_doi(self, doi: Doi) -> PackageId:
        _, hits = await self._search_xml(
            {"q": f'doi:"{doi.pid}"', "fl": "packageid,doi", "rows": "1", "start": "0"}
        )
        if hits:
            return hits[0].package
        # PASTA search indexes only newest revisions; older DOIs resolve via DataONE.
        if self._fallback is not None:
            self.note(
                f"{doi.pid} is not the newest revision of its package; it was resolved via DataONE."
            )
            package = await self._fallback.resolve_doi(doi)
            self.notes.extend(n for n in self._fallback.notes if n not in self.notes)
            return package
        raise ToolError(
            "not_found",
            f"No EDI package has the DOI {doi.pid}.",
            details={"doi": doi.pid},
            hint="Check the DOI, or search with edi_search_packages.",
        )


__all__ = ["ChangeKind", "LinkedPackage", "PackageChange", "PastaBackend", "ResourceReads"]
