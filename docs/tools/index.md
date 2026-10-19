# Tools

The tools available today, with the generated reference, package and metadata inspection, how package identifiers and scope names resolve, the PASTA and DataONE backends, error codes, and the roadmap of tools still to come.

* [Tool reference](reference.md) - Every edi-mcp tool with its inputs, result fields, upstream endpoints, key requirement and annotations, generated from the registry.
* [Discovery](discovery.md) - Find EDI data packages with edi_search_packages and walk the repository hierarchy with edi_list_scopes, edi_list_identifiers and edi_list_revisions, on PASTA or DataONE.
* [Packages, metadata and entities](packages.md) - Inspect one EDI package revision with edi_get_package, read its EML metadata in compact sections with edi_get_metadata, and list its data tables and files with columns, formats and checksums with edi_list_entities.
* [Identifiers and scope names](identifiers.md) - How EDI packages are identified (scope.identifier.revision, DOIs, portal and PASTA URLs), which forms edi-mcp accepts, and how scope names and LTER site codes resolve.
* [Backends: PASTA and DataONE](backends.md) - Why edi-mcp reads PASTA when an EDI API key is set and the anonymous DataONE replicas otherwise, how a result says which one answered, and the caveats of the DataONE fallback.
* [Utilities and errors](utilities.md) - Check the server, its key status and backend with edi_ping, and the stable error codes every edi-mcp tool can return.
* [Roadmap](roadmap.md) - Tools, resources and packaging that are planned for edi-mcp but not yet released: package and entity inspection, previews, downloads, citations and the key-only PASTA services.
