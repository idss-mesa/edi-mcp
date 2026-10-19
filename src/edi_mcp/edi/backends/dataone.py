"""DataONE backend: used, anonymously, when the call has no EDI API key (D1).

* Search and listings: the coordinating node's Solr index (JSON). Revisions
  are parsed from the ``id`` (a PASTA metadata URL) because ``obsoletedBy``
  and ``obsoletes`` are unreliable (missing on some superseded revisions,
  malformed on others; verified 2026-10-17), so results are de-duplicated per
  ``scope.identifier`` keeping the highest revision and ``numFound`` is only
  an upper bound.
* EML and system metadata: the member node holding the scope
  (``gmn.edirepository.org`` for ``edi``, ``gmn.lternet.edu`` otherwise), then
  the coordinating node as a fallback.
* Entities: EML names (PASTA entity id = MD5 of the name) enriched with size,
  SHA-1 and format from Solr data-object records when indexed.
* DOIs: the Solr ``resourceMap`` field, else the EDI citation service; DOI
  lookups read the resource map (``doi:10.6073/pasta/<md5>``) from the CN.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, unquote

from edi_mcp.edi.backends.base import (
    BULK_SCOPES,
    PASTA_PID_BASE,
    BackendBase,
    EntityInfo,
    SearchHit,
    SearchPage,
    SearchQuery,
    solr_phrase,
    year_end,
    year_start,
)
from edi_mcp.edi.eml import EmlEntity, entity_refs
from edi_mcp.edi.pid import Doi, PackageId
from edi_mcp.edi.xml import descendants, parse_xml
from edi_mcp.errors import EdiApiError, ToolError

if TYPE_CHECKING:
    from edi_mcp.edi.cache import CacheFamily
    from edi_mcp.edi.client import Fetched

SOURCE_FILTER = 'formatType:METADATA AND datasource:("urn:node:EDI" OR "urn:node:LTER")'
SEARCH_FIELDS = "id,title,pubDate,dateUploaded,beginDate,endDate,keywords,origin,resourceMap"
SEARCH_QF = "title^5 keywords^3 abstract^2 text"
ENTITY_FIELDS = "id,fileName,size,checksum,checksumAlgorithm,formatId"
MAX_LIST_ROWS = 10_000
_METADATA_ID = (
    r"https://pasta\.lternet\.edu/package/metadata/eml/"
    r"(?P<scope>[A-Za-z][A-Za-z0-9_-]*)/(?P<identifier>\d+)/(?P<revision>\d+)"
)
_METADATA_ID_RE = re.compile(f"^{_METADATA_ID}$")
#: Resource maps reference the EML through URL-encoded CN ``/resolve/`` links.
_EMBEDDED_ID_RE = re.compile(f"{_METADATA_ID}(?:$|[^/0-9])")
_LEGACY_ID_RE = re.compile(
    r"^(?P<scope>[A-Za-z][A-Za-z0-9_-]*)\.(?P<identifier>\d+)\.(?P<revision>\d+)$"
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_CITE_DOI_RE = re.compile(r"10\.6073/pasta/([0-9a-f]{32})", re.IGNORECASE)
_SOLR_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')
LAG_NOTE = (
    "Served from DataONE replicas (no EDI API key): new uploads can take days to appear; "
    "set EDI_API_KEY to read PASTA directly."
)


def solr_escape(value: str) -> str:
    return _SOLR_SPECIAL.sub(r"\\\1", value)


def _package_from_id(pid: str, *, embedded: bool = False) -> PackageId | None:
    """The package of a DataONE metadata identifier: a PASTA metadata URL, or (records the
    old LTER node registered, ~15% of the index on 2026-10-19) ``scope.identifier.revision``."""
    m = _EMBEDDED_ID_RE.search(unquote(pid)) if embedded else _METADATA_ID_RE.match(pid)
    if not m and not embedded:
        m = _LEGACY_ID_RE.match(pid)
    if not m:
        return None
    return PackageId(m.group("scope"), int(m.group("identifier")), int(m.group("revision")))


def _date(value: Any) -> str | None:
    """Solr dates are ``YYYY-MM-DDT00:00:00Z``; keep the date part. Malformed values
    (``+20071203-01-01T…`` on some legacy records) are dropped."""
    if not isinstance(value, str):
        return None
    m = _DATE_RE.match(value)
    return m.group(0) if m else None


def _strs(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)] if value else []


class DataOneBackend(BackendBase):
    name = "dataone"

    @property
    def solr_url(self) -> str:
        return self.config.edi.dataone_cn_url.rstrip("/") + "/query/solr/"

    def not_found_hint(self) -> str | None:
        return (
            "DataONE may not have this package yet (replication lags EDI, and some scopes are "
            "not replicated); set EDI_API_KEY to read PASTA directly."
        )

    async def _solr(self, params: dict[str, str], *, cache: CacheFamily) -> dict[str, Any]:
        fetched = await self.client.get(
            self.solr_url, {**params, "wt": "json"}, cache=cache, stats=self.stats
        )
        try:
            body = json.loads(fetched.body)
            response = body["response"]
        except (ValueError, KeyError, TypeError):
            raise EdiApiError(
                fetched.status,
                "Solr response is not JSON",
                "/cn/v2/query/solr/",
                kind="decode",
                content_type=fetched.content_type,
                service="DataONE",
            ) from None
        return response if isinstance(response, dict) else {}

    def _id_prefix(self, *parts: str | int) -> str:
        path = "/".join(str(p) for p in parts)
        return f"id:{solr_escape(f'{PASTA_PID_BASE}/metadata/eml/{path}/')}*"

    async def _get_object(self, pid: str, scope: str, *, max_bytes: int | None = None) -> Fetched:
        """A DataONE object from the scope's member node, else from the CN."""
        encoded = quote(pid, safe="")
        try:
            return await self.client.get(
                f"{self.member_node(scope)}/object/{encoded}",
                cache="metadata",
                stats=self.stats,
                max_bytes=max_bytes,
            )
        except EdiApiError as exc:
            if exc.status != 404:
                raise
        return await self.client.get(
            f"{self.config.edi.dataone_cn_url.rstrip('/')}/object/{encoded}",
            cache="metadata",
            stats=self.stats,
            max_bytes=max_bytes,
        )

    # ------------------------------------------------------------------ search

    def search_filter(self, query: SearchQuery) -> str:
        clauses = [SOURCE_FILTER, "-obsoletedBy:*"]
        if query.scope:
            clauses.append(self._id_prefix(query.scope))
        if query.author:
            # investigatorText holds creators' last names, tokenized (case-insensitive).
            clauses.append(f"investigatorText:{solr_phrase(query.author)}")
        if query.end_year is not None:
            clauses.append(f"beginDate:[* TO {year_end(query.end_year)}]")
        if query.start_year is not None:
            clauses.append(f"endDate:[{year_start(query.start_year)} TO *]")
        if query.bbox is not None:
            b = query.bbox
            clauses += [
                f"northBoundCoord:[{b.south} TO *]",
                f"southBoundCoord:[* TO {b.north}]",
                f"eastBoundCoord:[{b.west} TO *]",
                f"westBoundCoord:[* TO {b.east}]",
            ]
        if not query.scope and query.exclude_bulk:
            clauses += [f"-{self._id_prefix(s)}" for s in BULK_SCOPES]
        return " AND ".join(clauses)

    async def search(self, query: SearchQuery) -> SearchPage:
        params = {
            "defType": "edismax",
            "q": query.query_text,
            "qf": SEARCH_QF,
            "fq": self.search_filter(query),
            "fl": SEARCH_FIELDS,
            "rows": str(query.limit),
            "start": str(query.offset),
        }
        if query.sort != "relevance":
            # pubDate became an unsortable range field on 2026-10-19 ("Sorting not supported
            # on SpatialField"); dateUploaded (when this revision reached DataONE) still sorts.
            params["sort"] = "dateUploaded desc" if query.sort == "newest" else "dateUploaded asc"
            self.note(
                "DataONE sorts by upload date (when each revision reached DataONE); its "
                "publication-date field is not sortable."
            )
        response = await self._solr(params, cache="search")
        best: dict[str, SearchHit] = {}
        for doc in response.get("docs") or []:
            package = _package_from_id(str(doc.get("id", "")))
            if package is None:
                continue
            current = best.get(package.series)
            if current is not None and (current.package.revision or 0) >= (package.revision or 0):
                continue
            maps = _strs(doc.get("resourceMap"))
            best[package.series] = SearchHit(
                package=package,
                title=doc.get("title"),
                pub_date=_date(doc.get("pubDate")),
                doi=next((m for m in maps if m.startswith("doi:")), None),
                begin_date=_date(doc.get("beginDate")),
                end_date=_date(doc.get("endDate")),
                keywords=_strs(doc.get("keywords")),
                authors=_strs(doc.get("origin")),
                uploaded=_date(doc.get("dateUploaded")),
            )
        self.note(LAG_NOTE)
        found = response.get("numFound")
        return SearchPage(
            list(best.values()),
            found if isinstance(found, int) else None,
            False,
            query.offset,
            query.limit,
        )

    # ------------------------------------------------------------------ listings

    async def _ids(self, q: str, fq: str | None = None) -> list[PackageId]:
        params = {"q": q, "fl": "id", "rows": str(MAX_LIST_ROWS)}
        if fq:
            params["fq"] = fq
        response = await self._solr(params, cache="listings")
        found = response.get("numFound")
        if isinstance(found, int) and found > MAX_LIST_ROWS:
            self.note(f"DataONE listed only the first {MAX_LIST_ROWS} of {found} records.")
        out = []
        for doc in response.get("docs") or []:
            package = _package_from_id(str(doc.get("id", "")))
            if package is not None:
                out.append(package)
        return out

    async def list_identifiers(self, scope: str) -> list[int]:
        ids = await self._ids(self._id_prefix(scope), f"{SOURCE_FILTER} AND -obsoletedBy:*")
        self.note(LAG_NOTE)
        identifiers = sorted({p.identifier for p in ids})
        if not identifiers:
            raise ToolError(
                "not_found",
                f"DataONE has no packages in scope {scope!r}.",
                details={"identifier": scope, "backend": "dataone"},
                hint=self.not_found_hint(),
            )
        return identifiers

    async def list_revisions(self, scope: str, identifier: int) -> list[int]:
        ids = await self._ids(self._id_prefix(scope, identifier))
        self.note(LAG_NOTE)
        return sorted({p.revision for p in ids if p.revision is not None})

    # ------------------------------------------------------------------ package

    async def read_eml(self, package: PackageId) -> bytes:
        try:
            fetched = await self._get_object(
                self.metadata_pid(package),
                package.scope,
                max_bytes=self.config.limits.max_eml_bytes,
            )
        except EdiApiError as exc:
            raise self.not_found(exc, "package", str(package)) from None
        return fetched.body

    async def list_entities(
        self, package: PackageId, refs: list[EmlEntity] | None = None
    ) -> list[EntityInfo]:
        """Entities from the EML (``refs`` when the caller already parsed it), enriched
        with size, SHA-1 and format from DataONE's index."""
        if refs is None:
            refs = entity_refs(
                await self.read_eml(package), source=self.metadata_pid(package), service="DataONE"
            )
        response = await self._solr(
            {
                "q": f'isDocumentedBy:"{self.metadata_pid(package)}"',
                "fl": ENTITY_FIELDS,
                "rows": "1000",
            },
            cache="metadata",
        )
        indexed = {str(d.get("id")): d for d in response.get("docs") or []}
        out = []
        for ref in refs:
            if ref.entity_id is None:
                continue
            url = self.data_url(package, ref.entity_id)
            doc = indexed.get(url, {})
            size = doc.get("size")
            sha1 = doc.get("checksum") if doc.get("checksumAlgorithm") == "SHA-1" else None
            out.append(
                EntityInfo(
                    entity_id=ref.entity_id,
                    name=ref.name,
                    size=size if isinstance(size, int) else ref.size,
                    sha1=str(sha1).lower() if sha1 else None,
                    format_id=doc.get("formatId") or ref.format,
                    object_name=doc.get("fileName") or ref.object_name,
                    entity_type=ref.entity_type,
                    url=url,
                )
            )
        if refs and not indexed:
            self.note(
                "DataONE's index has no records for these entities yet; sizes come from the EML "
                "and checksums from each entity's system metadata."
            )
        return out

    async def entity_checksum(self, package: PackageId, entity_id: str) -> str | None:
        pid = quote(self.data_url(package, entity_id), safe="")
        try:
            fetched = await self.client.get(
                f"{self.member_node(package.scope)}/meta/{pid}", cache="metadata", stats=self.stats
            )
        except EdiApiError as exc:
            raise self.not_found(exc, "entity", f"{package}/{entity_id}") from None
        root = parse_xml(fetched.body, source="/mn/v2/meta", service="DataONE")
        checksum = next(descendants(root, "checksum"), None)
        if checksum is None or (checksum.get("algorithm") or "").upper() != "SHA-1":
            return None
        return " ".join(checksum.text.split()).lower() if checksum.text else None

    async def package_doi(self, package: PackageId) -> str | None:
        response = await self._solr(
            {"q": f'id:"{self.metadata_pid(package)}"', "fl": "id,resourceMap", "rows": "1"},
            cache="metadata",
        )
        for doc in response.get("docs") or []:
            for value in _strs(doc.get("resourceMap")):
                if value.startswith("doi:"):
                    return value
        return await self._doi_from_citation(package)

    async def _doi_from_citation(self, package: PackageId) -> str | None:
        """The EDI citation service (anonymous) knows DOIs DataONE has not indexed yet."""
        try:
            fetched = await self.client.get(
                f"{self.config.edi.cite_url.rstrip('/')}/{package.package_id}",
                accept="application/json",
                cache="citations",
                stats=self.stats,
            )
            doi = json.loads(fetched.body).get("doi")
        except (EdiApiError, ValueError, AttributeError):
            doi = None
        m = _CITE_DOI_RE.search(doi) if isinstance(doi, str) else None
        if m is None:
            self.note("Neither DataONE nor the EDI citation service reported a DOI.")
            return None
        self.note("The DOI came from the EDI citation service (DataONE has not indexed it).")
        return f"doi:10.6073/pasta/{m.group(1).lower()}"

    def entity_source_url(self, package: PackageId, entity_id: str) -> str:
        """Without a key, entity bytes come from the scope's GMN member node."""
        return self.anonymous_data_url(package, entity_id)

    async def read_report(self, package: PackageId) -> bytes:
        """PASTA's quality report, replicated on the member node (served anonymously)."""
        try:
            fetched = await self._get_object(
                self.report_pid(package),
                package.scope,
                max_bytes=self.config.limits.max_eml_bytes,
            )
        except EdiApiError as exc:
            raise self.not_found(exc, "quality report", str(package)) from None
        return fetched.body

    async def resolve_doi(self, doi: Doi) -> PackageId:
        try:
            fetched = await self.client.get(
                f"{self.config.edi.dataone_cn_url.rstrip('/')}/object/{quote(doi.pid, safe='')}",
                cache="metadata",
                stats=self.stats,
            )
        except EdiApiError as exc:
            raise self.not_found(exc, "DOI", doi.pid) from None
        root = parse_xml(fetched.body, source="/cn/v2/object", service="DataONE")
        for element in root.iter():
            for value in element.attrib.values():
                package = _package_from_id(value, embedded=True)
                if package is not None:
                    return package
        raise ToolError(
            "not_found",
            f"The resource map {doi.pid} names no EML document.",
            details={"doi": doi.pid},
        )


__all__ = ["DataOneBackend", "solr_escape"]
