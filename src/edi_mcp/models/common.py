"""Base models, the result envelope, and shared input types.

Naming (neon-mcp D1, kept): input fields are snake_case in every
``inputSchema`` and also accept the camelCase spelling; output keys are
camelCase, including edi-mcp's additions (``nextSteps``, ``page.nextOffset``,
``packageId``).
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import (
    AliasChoices,
    AliasGenerator,
    BaseModel,
    ConfigDict,
    Field,
)
from pydantic.alias_generators import to_camel


def _validation_alias(name: str) -> AliasChoices:
    camel = to_camel(name)
    return AliasChoices(name, camel) if camel != name else AliasChoices(name)


class EdiInput(BaseModel):
    """Base for every tool input: snake_case advertised, camelCase accepted, extras rejected."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        alias_generator=AliasGenerator(validation_alias=_validation_alias),
    )


class EdiOutput(BaseModel):
    """Base for every output object; dumped ``by_alias`` so keys are camelCase."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    #: Name of the list field :func:`edi_mcp.registry.fit_to_budget` may shorten.
    budget_list: ClassVar[str | None] = None
    #: Item fields nulled (from the tail) before items are dropped.
    budget_elide_fields: ClassVar[tuple[str, ...]] = ()
    #: Flag set on the payload when elision happened (e.g. ``urls_elided``).
    budget_elide_flag: ClassVar[str | None] = None
    #: The Page field describing ``budget_list``.
    budget_page: ClassVar[str] = "page"
    #: Next step added when ``budget_list`` is trimmed, for tools without offset/limit;
    #: ``{next_offset}`` is filled in. ``None`` = "call again with offset=…".
    budget_next_step: ClassVar[str | None] = None


class Page(EdiOutput):
    """Pagination state of one list in a result."""

    total: int | None = Field(None, description="Total items available, when known.")
    returned: int = Field(description="Items in this result.")
    offset: int = Field(description="Offset of the first returned item.")
    limit: int = Field(description="Page size that was applied.")
    truncated: bool = Field(description="True when more items exist beyond this page.")
    next_offset: int | None = Field(
        None, description="Pass as offset to get the next page; absent when there is none."
    )
    truncated_reason: Literal["limit", "budget"] | None = Field(
        None,
        description="'limit' = page size reached; 'budget' = trimmed to the result-size budget.",
    )


class Resolved(EdiOutput):
    """Echo of an input normalized or fuzzy-resolved to an EDI identifier."""

    field: str
    input: str
    code: str
    confidence: float


Backend = Literal["pasta", "dataone", "cite", "local", "mixed"]


class Source(EdiOutput):
    """Where a result came from."""

    endpoints: list[str] = Field(
        default_factory=list,
        description="Upstream endpoints called (method, host and path; never a query or credential).",
    )
    backend: Backend = Field(
        "local",
        description="pasta (EDI API key), dataone (anonymous replicas), cite (citation service), "
        "local (no upstream call) or mixed.",
    )
    cached: bool = False
    derived: list[str] = Field(
        default_factory=list,
        description="Fields computed by edi-mcp rather than returned by EDI.",
    )


class ToolResultBase(EdiOutput):
    """Envelope carried by every tool result."""

    resolved: list[Resolved] = Field(
        default_factory=list, description="Inputs normalized or resolved to EDI identifiers."
    )
    notes: list[str] = Field(
        default_factory=list, description="Caveats: backend limits, index lag, fallbacks used."
    )
    next_steps: list[str] = Field(default_factory=list, description="Concrete follow-up calls.")
    source: Source | None = None
