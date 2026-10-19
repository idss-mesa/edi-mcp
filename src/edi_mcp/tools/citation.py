"""``edi_get_citation``: a formatted citation from cite.edirepository.org (anonymous)."""

from __future__ import annotations

from pydantic import Field

from edi_mcp.context import ToolContext
from edi_mcp.edi.backends import backend_for, resolve_package
from edi_mcp.edi.backends.base import CitationStyle
from edi_mcp.models.common import EdiOutput, Resolved, ToolResultBase
from edi_mcp.registry import register_tool
from edi_mcp.tools._common import merge_notes, portal_url, source
from edi_mcp.tools.packages import PackageArgs, RevisionFrom

DATA_POLICY = (
    "Cite the exact revision you used, by its DOI. EDI data carry their own terms in each "
    "package's intellectual rights (edi_get_metadata include=['rights']); see "
    "https://edirepository.org/about/edi-policy."
)


class CitationIn(PackageArgs):
    style: CitationStyle = Field("ESIP", description="ESIP (default), DRYAD or BIBTEX.")


class CitationParts(EdiOutput):
    authors: str | None = None
    year: str | None = None
    title: str | None = None
    version: str | None = None
    publisher: str | None = None
    doi: str | None = None


class CitationResult(ToolResultBase):
    package_id: str
    revision_from: RevisionFrom
    style: CitationStyle
    citation: str = Field(description="The formatted citation (BibTeX entry for BIBTEX).")
    parts: CitationParts
    doi_url: str | None = None
    portal_url: str


@register_tool(
    "edi_get_citation",
    title="Cite an EDI data package",
    description=(
        "A formatted citation for one package revision from the EDI citation service: ESIP "
        "(default), DRYAD or BibTeX, plus its parts (authors, year, title, version, publisher, "
        "DOI). Needs no key, though a key lets 'newest' come from PASTA. Restricted packages "
        "have no citation. Next: cite the DOI in your work and check the license with "
        "edi_get_metadata include=['rights']."
    ),
    input_model=CitationIn,
    output_model=CitationResult,
    surface="citation",
    endpoints=[
        "GET cite.edirepository.org/cite/{packageId}",
        "GET pasta.lternet.edu/package/eml/{scope}/{id}",
        "GET cn.dataone.org/cn/v2/query/solr/",
    ],
)
async def edi_get_citation(args: CitationIn, ctx: ToolContext) -> CitationResult:
    backend = backend_for(ctx)
    resolved = await resolve_package(backend, args.package, args.revision)
    package = resolved.package
    echoes = list(resolved.resolved)
    if resolved.raw.strip() != package.package_id:
        echoes.append(
            Resolved(field="package", input=args.package, code=package.package_id, confidence=1.0)
        )
    text = await backend.citation(package, args.style)
    fields = await backend.citation_fields(package)
    doi_url = None
    if fields.doi and fields.doi.startswith("doi:"):
        doi_url = "https://doi.org/" + fields.doi.removeprefix("doi:")
    src = source(ctx)
    # The citation itself always comes from the citation service; resolving a series to its
    # newest revision also asked the call's backend.
    src.backend = "cite" if all("cite.edirepository.org" in e for e in src.endpoints) else "mixed"
    return CitationResult(
        package_id=package.package_id,
        revision_from=resolved.revision_from,
        style=args.style,
        citation=text,
        parts=CitationParts(
            authors=fields.authors,
            year=fields.year,
            title=fields.title,
            version=fields.version,
            publisher=fields.publisher,
            doi=fields.doi,
        ),
        doi_url=doi_url,
        portal_url=portal_url(ctx, package),
        resolved=echoes,
        notes=merge_notes(backend.notes, [DATA_POLICY]),
        next_steps=[f"edi_get_metadata(package='{package.package_id}', include=['rights'])"],
        source=src,
    )
