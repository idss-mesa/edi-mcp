"""Server instructions returned by ``server/discover`` (kept under 1 200 characters)."""

from __future__ import annotations

SERVER_INSTRUCTIONS = (
    "edi-mcp exposes the Environmental Data Initiative (EDI) repository: LTER and EDI ecological "
    "data packages with EML metadata. Packages are identified as scope.identifier.revision "
    "(knb-lter-hbr.14.22, edi.1.1); tools also accept scope/identifier/revision, "
    "doi:10.6073/pasta/... DOIs and portal URLs, and echo the normalized packageId in `resolved`. "
    "Scopes also accept LTER site codes and names (JRN, 'Jornada'). "
    "Typical flow: edi_search_packages -> edi_get_package / edi_get_metadata -> edi_list_entities "
    "-> edi_preview_entity or edi_download_entities (stdio only) -> edi_get_citation. Since "
    "2026-07-30 EDI's PASTA API requires an API key: with EDI_API_KEY set, edi-mcp serves from "
    "PASTA; without one it serves search, metadata, entities and citations from DataONE "
    "replicas (which can lag new uploads), and quality reports, lineage, change feeds and read "
    "counts return auth_required. Every result is compact and paginated (page.nextOffset), says "
    "which backend served it in source.backend, carries notes, and ends with nextSteps. Call "
    "edi_ping to learn whether a key is configured; read edi://guide/api-key to set one up and "
    "edi://guide/package-identifiers for identifier forms."
)
