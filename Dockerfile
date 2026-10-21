# edi-mcp: stateless Streamable HTTP deployment image.
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.13-slim
LABEL org.opencontainers.image.title="edi-mcp" \
      org.opencontainers.image.description="MCP server for the EDI PASTA+ data repository" \
      org.opencontainers.image.source="https://github.com/idss-mesa/edi-mcp" \
      org.opencontainers.image.licenses="MIT" \
      io.modelcontextprotocol.server.name="io.github.idss-mesa/edi-mcp"
RUN useradd --create-home --uid 10001 edi
COPY --from=build --chown=edi:edi /app/.venv /app/.venv
USER edi
WORKDIR /home/edi
ENV PATH="/app/.venv/bin:$PATH" \
    EDI_MCP_SERVER__TRANSPORT=http \
    EDI_MCP_SERVER__BIND_ADDRESS=0.0.0.0 \
    EDI_MCP_SERVER__BIND_PORT=8080 \
    EDI_MCP_SERVER__LOG_LEVEL=info
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"
CMD ["edi-mcp", "--transport", "http", "--bind-address", "0.0.0.0"]
