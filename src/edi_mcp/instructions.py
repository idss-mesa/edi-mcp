"""Server instructions returned by ``server/discover`` (kept under 1 200 characters)."""

from __future__ import annotations

SERVER_INSTRUCTIONS = (
    "edi-mcp exposes the Environmental Data Initiative (EDI) repository: LTER and EDI ecological "
    "data packages with EML metadata. Packages are scope.identifier.revision "
    "(knb-lter-hbr.14.22); tools also accept scope/identifier/revision, doi:10.6073/pasta/... "
    "DOIs and portal URLs, and echo the normalized packageId in `resolved`. Scopes also accept "
    "LTER site codes and names (JRN, 'Jornada'). Typical flow: edi_search_packages -> "
    "edi_get_package / edi_get_metadata -> edi_list_entities -> edi_preview_entity or "
    "edi_download_entities (stdio only) -> edi_get_citation. Since 2026-07-30 EDI's PASTA API "
    "requires an API key: with EDI_API_KEY set, edi-mcp serves from PASTA; without one it serves "
    "search, metadata, entities, previews, quality reports and citations from DataONE replicas "
    "(which can lag new uploads), and lineage, change feeds, read counts and package zips "
    "return auth_required. Results are compact and paginated (page.nextOffset), name the "
    "backend in source.backend, carry notes, and end with nextSteps. Call edi_ping to learn "
    "whether a key is configured. Read edi://guide/agent-workflow for worked examples, "
    "edi://guide/api-key to set up a key and edi://guide/search-syntax for queries."
)
