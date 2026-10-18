"""PASTA+ backend: used when the call has an EDI API key (DESIGN.md D1).

Every request goes to ``{pasta_base_url}/package/…`` with the call's key,
which the client turns into an ``edi-token`` cookie (D4). Response formats
were verified on 2026-10-17 (RESEARCH.md section 1): listings are
newline-separated text, entity names and sizes are ``id,value`` CSV, search
is Solr XML (``<resultset numFound>``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    from edi_mcp.edi.client import EdiClient, Fetched

SEARCH_FIELDS = "packageid,title,pubdate,doi,begindate,enddate,scope,keyword,author"


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

    async def list_entities(self, package: PackageId) -> list[EntityInfo]:
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


__all__ = ["PastaBackend"]
