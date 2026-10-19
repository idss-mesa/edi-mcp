# Deploy

Run edi-mcp as a hosted, stateless HTTP service behind TLS, and the security model operators rely on.

* [Hosted HTTP deployment](hosted-http.md) - Run edi-mcp as a stateless Streamable HTTP service behind a TLS reverse proxy: binding, public_base_url, host allow-lists, per-caller EDI API keys and health endpoints.
* [Security](security.md) - How edi-mcp handles EDI API keys and edi-tokens, which hosts receive credentials, how URLs, logs and upstream errors are scrubbed, how untrusted XML is parsed, and what keeps test fixtures free of secrets.
