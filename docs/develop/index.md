# Develop

Architecture, adding a tool, the hermetic test suite with recorded fixtures, and how to contribute.

* [Architecture](architecture.md) - The module map of edi-mcp: SDK adapter and tool registry, per-call context and backend choice, the PASTA and DataONE backends, the one upstream HTTP client, identifier and scope resolution, and the transports.
* [Adding a tool](adding-tools.md) - The checklist for a new edi-mcp tool: input and output models, registration rules, backend calls, fixtures and tests, the conformance sets, and regenerating the docs.
* [Testing](testing.md) - edi-mcp's hermetic test suite, the FixtureRouter that replays recorded PASTA and DataONE traffic, recording and checking fixtures, opt-in live tests, the coverage, type and lint gates, CI jobs and the documentation checks.
* [Contributing](contributing.md) - Branch and pull-request rules, the checks to run before pushing, the design and research records, the two change logs, documentation updates and versioning for edi-mcp.
