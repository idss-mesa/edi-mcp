---
title: "Adding a tool"
description: "The checklist for a new edi-mcp tool: input and output models, registration rules, backend calls, fixtures and tests, the conformance sets, and regenerating the docs."
type: Guide
tags:
  - develop
  - tools
  - checklist
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: repo
    resource: "https://github.com/idss-mesa/edi-mcp/blob/main/src/edi_mcp/tools/discovery.py"
    title: "edi-mcp discovery tools (src/edi_mcp/tools/discovery.py)"
    author: "team:idss-mesa"
  - id: mcp-tools
    resource: "https://modelcontextprotocol.io/specification/2026-07-28/server/tools"
    title: "MCP 2026-07-28 — Tools"
    author: "team:modelcontextprotocol"
status: stable
---

# Adding a tool

[`edi_list_scopes`](../tools/reference.md#edi_list_scopes) in
`src/edi_mcp/tools/discovery.py` is a small real example; this is its shape.

## 1. Models

```python
class ListScopesIn(EdiInput):             # snake_case fields; extras rejected
    kind: ScopeKind | None = Field(
        None, description="Only one kind: lter (LTER sites), edi (general EDI submissions), ..."
    )


class ListScopesResult(ToolResultBase):   # envelope: resolved, notes, nextSteps, source
    budget_list: ClassVar[str | None] = "scopes"

    scopes: list[ScopeInfo]
    page: Page
    live: bool = Field(description="True when PASTA listed the scopes just now; ...")
    snapshot_as_of: str = Field(description="Date of the snapshot ...")   # dumped as snapshotAsOf
```

Inputs subclass `EdiInput` and use snake_case; outputs subclass
`ToolResultBase` and are dumped in camelCase with `None` omitted. Every input
field needs a `description`: it is what the model reads. A result with a long
list declares `budget_list` so the registry can trim it to the size budget
(see [Architecture](architecture.md#result-budget)).

## 2. Register the handler

```python
@register_tool(
    "edi_list_scopes",
    title="List EDI scopes",
    description=(
        "List the repository's scopes (knb-lter-hbr, edi, ...) with name, kind, ... "
        "Next: call edi_search_packages(scope=...) or edi_list_identifiers(scope=...)."
    ),
    input_model=ListScopesIn,
    output_model=ListScopesResult,
    surface="discovery",
    endpoints=["GET pasta.lternet.edu/package/eml"],
)
async def edi_list_scopes(args: ListScopesIn, ctx: ToolContext) -> ListScopesResult:
    backend = backend_for(ctx)
    if isinstance(backend, PastaBackend):
        names = await backend.list_scopes()
    else:
        ...   # DataONE has no scope listing: use the dated snapshot and say so in notes
```

The registry checks each declaration at import time:

* the name matches `^edi_[a-z_]+$`;
* the description is at most 600 characters and ends with a sentence starting
  `Next:`;
* the input model subclasses `EdiInput` and the output model `ToolResultBase`;
* `surface` is a known family.

Also:

* keep the annotations honest (`read_only`, `destructive`, `idempotent`,
  `open_world`);
* list every upstream endpoint the handler can call, on both backends;
* set `requires_key=True` for PASTA-only tools, so the registry fails fast with
  `auth_required` when the call has no key;
* restrict stdio-only tools with `transports=("stdio",)`.

Handlers call `backend_for(ctx)` and `resolve_scope` / `resolve_reference` /
`resolve_package`, never the HTTP client directly. Build `source` with
`tools._common.source(ctx)`, and fill `notes` (backend caveats, what was
assumed) and `nextSteps` (concrete follow-up calls). Finally, import the module
in `tools/__init__.py`.

## 3. Fixtures and tests

* Add the tool's real calls to `TOOL_SCENARIOS` in
  `scripts/record_fixtures.py` (on both backends where the tool supports both)
  and re-record. Fixtures come only from the recorder; see
  [Testing](testing.md).
* Test through `tests.helpers.call_ok`, which asserts success and validates the
  payload against the tool's `outputSchema`, and `call_err` for error codes.
  Cover the happy path on both backends, each filter, paging, error mapping
  and, for key-only tools, the `auth_required` fail-fast.
* Update the `KEY_TOOLS` and `WRITE_TOOLS` sets in
  `tests/test_spec_conformance_2026_07_28.py`, which check the
  `readOnlyHint` and requires-key metadata of every tool.

## 4. Regenerate the docs

```bash
uv run python scripts/gen_tools_reference.py   # docs/tools/reference.md
uv run python scripts/gen_llms_txt.py          # docs/llms.txt, docs/llms-full.txt
```

Describe the tool on its family page under `docs/tools/` and add a dated entry
to `docs/log.md`. The docs workflow fails when a generated file has drifted
from its sources.
