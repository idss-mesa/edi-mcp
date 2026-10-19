# Tools

All sixteen tools, with the generated reference: discovery, package and metadata inspection, previews and downloads, citations, quality reports and lineage, the change feed and read counts, how identifiers and scope names resolve, the PASTA and DataONE backends, error codes, and what remains on the roadmap.

* [Tool reference](reference.md) - Every edi-mcp tool with its inputs, result fields, upstream endpoints, key requirement and annotations, generated from the registry.
* [Discovery](discovery.md) - Find EDI data packages with edi_search_packages and walk the repository hierarchy with edi_list_scopes, edi_list_identifiers and edi_list_revisions, on PASTA or DataONE.
* [Packages, metadata and entities](packages.md) - Inspect one EDI package revision with edi_get_package, read its EML metadata in compact sections with edi_get_metadata, and list its data tables and files with columns, formats and checksums with edi_list_entities.
* [Previews and downloads](data.md) - Read the first rows of a delimited data entity with edi_preview_entity on either backend, and save entities, their EML or a whole package zip into the download directory with edi_download_entities and edi_download_package (stdio only).
* [Citations, quality reports and lineage](citation-and-quality.md) - Cite a package revision with edi_get_citation, read PASTA's quality checks with edi_get_quality_report (with or without a key), and follow provenance with edi_get_lineage (key required).
* [Change feed and read counts](feeds.md) - List packages inserted, updated or deleted in PASTA during a date window with edi_recent_changes, and see how often a package series or revision has been read with edi_get_read_counts; both need an EDI API key.
* [Identifiers and scope names](identifiers.md) - How EDI packages are identified (scope.identifier.revision, DOIs, portal and PASTA URLs), which forms edi-mcp accepts, and how scope names and LTER site codes resolve.
* [Backends: PASTA and DataONE](backends.md) - Why edi-mcp reads PASTA when an EDI API key is set and the anonymous DataONE replicas otherwise, how a result says which one answered, and the caveats of the DataONE fallback.
* [Utilities and errors](utilities.md) - Check the server, its key status and backend with edi_ping, and the stable error codes every edi-mcp tool can return.
* [Roadmap](roadmap.md) - What remains planned for edi-mcp after the sixteen tools: more edi:// resources and templates, prompts, a server.json for the MCP Registry, a Docker image and the v0.1.0 release.
