"""MCP prompts: three task recipes that steer an agent through the tools (D22)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from mcp import types as t

from edi_mcp.errors import ToolError

STYLES = ("ESIP", "DRYAD", "BIBTEX")
_YEARS_RE = re.compile(r"^\d{4}(\s*-\s*\d{4})?$")


@dataclass(frozen=True)
class _Arg:
    name: str
    description: str
    required: bool = False


@dataclass(frozen=True)
class _Prompt:
    name: str
    title: str
    description: str
    arguments: tuple[_Arg, ...]


PROMPTS: tuple[_Prompt, ...] = (
    _Prompt(
        "edi_cite_package",
        "Cite an EDI data package",
        "Produce a citation (and BibTeX) for one revision of an EDI package, with its DOI and rights.",
        (
            _Arg("package", "Package id, DOI or portal URL, e.g. knb-lter-hbr.14.22.", True),
            _Arg("style", "ESIP (default), DRYAD or BIBTEX."),
        ),
    ),
    _Prompt(
        "edi_find_data",
        "Find EDI data for a question",
        "Go from a research question to candidate EDI packages, their tables and coverage.",
        (
            _Arg("question", "The research question in plain language.", True),
            _Arg("place", "LTER site, scope, region or bounding box to focus on."),
            _Arg("years", "A year or range of years, e.g. 1990-2010."),
        ),
    ),
    _Prompt(
        "edi_plan_download",
        "Plan an EDI download",
        "Size, preview and (on stdio) download the tables of one EDI package, then cite it.",
        (
            _Arg("package", "Package id, DOI or portal URL.", True),
            _Arg("entities", "Comma-separated entity names or ids (default: all)."),
        ),
    ),
)


def list_prompts() -> list[t.Prompt]:
    return [
        t.Prompt(
            name=p.name,
            title=p.title,
            description=p.description,
            arguments=[
                t.PromptArgument(name=a.name, description=a.description, required=a.required)
                for a in p.arguments
            ],
        )
        for p in PROMPTS
    ]


def _validate(prompt: _Prompt, arguments: Mapping[str, str]) -> dict[str, str]:
    known = {a.name for a in prompt.arguments}
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise ToolError(
            "invalid_argument", f"Unknown argument(s) for {prompt.name}: {', '.join(unknown)}."
        )
    values = {k: str(v).strip() for k, v in arguments.items() if v is not None and str(v).strip()}
    missing = [a.name for a in prompt.arguments if a.required and a.name not in values]
    if missing:
        raise ToolError(
            "invalid_argument",
            f"Missing required argument(s) for {prompt.name}: {', '.join(missing)}.",
        )
    if "style" in values:
        values["style"] = values["style"].upper()
        if values["style"] not in STYLES:
            raise ToolError("invalid_argument", "style must be ESIP, DRYAD or BIBTEX.")
    if "years" in values and not _YEARS_RE.match(values["years"]):
        raise ToolError("invalid_argument", "years must be YYYY or YYYY-YYYY.")
    return values


def _years(value: str) -> str:
    start, _, end = value.partition("-")
    start, end = start.strip(), (end.strip() or start.strip())
    return f"start_year={start}, end_year={end}"


def _render(name: str, v: Mapping[str, str]) -> str:
    if name == "edi_find_data":
        extra = "".join(
            f"\n- {label}: {v[key]}"
            for key, label in (("place", "Place"), ("years", "Years"))
            if key in v
        )
        filters = []
        if "place" in v:
            filters.append("scope= for an LTER site or scope name, or bbox= for a region")
        if "years" in v:
            filters.append(_years(v["years"]))
        hint = f" with {'; '.join(filters)}" if filters else ""
        return (
            f"Research question: {v['question']}{extra}\n\n"
            "Use the edi-mcp tools to find EDI data packages that can answer it:\n"
            "1. edi_ping: note whether an EDI API key is configured (without one, results come "
            "from DataONE and can lag new uploads).\n"
            f"2. edi_search_packages{hint}. Words are ORed: join required words with AND, and "
            "quote phrases. Try two or three phrasings and follow page.nextOffset if the first "
            "page is not conclusive (edi://guide/search-syntax).\n"
            "3. For the best 2-4 packages, edi_get_metadata(include=['overview', 'coverage', "
            "'methods']) to check what was measured, where and when.\n"
            "4. edi_list_entities(include_attributes=true) for the most promising one, and "
            "edi_preview_entity on its main table to confirm the columns and units.\n"
            "5. Finish with a table of candidate packages (packageId, title, years, place, "
            "main tables), the caveats from the results' notes, and edi_get_citation for each."
        )
    if name == "edi_cite_package":
        style = v.get("style", "ESIP")
        return (
            f"Cite the EDI data package {v['package']}.\n"
            f"1. edi_get_citation(package={v['package']!r}, style={style!r}). If the package "
            "names no revision, the newest is used: say which revision was cited.\n"
            "2. edi_get_metadata(package=..., include=['rights']) and summarise the "
            "intellectual rights in one sentence.\n"
            "Present the citation text, the DOI link and the rights. Cite the DOI, never a "
            "download URL (edi://guide/citing-edi-data)."
        )
    wanted = f" (entities: {v['entities']})" if "entities" in v else ""
    entities_arg = (
        f", entities={[e.strip() for e in v['entities'].split(',') if e.strip()]!r}"
        if "entities" in v
        else ""
    )
    return (
        f"Plan a download of EDI package {v['package']}{wanted}.\n"
        "1. edi_ping: is a key configured, and are downloads enabled (stdio only)?\n"
        f"2. edi_list_entities(package={v['package']!r}, include_checksums=true) to list each "
        "entity's file name, size and SHA-1, and add up the total.\n"
        "3. edi_preview_entity on each table to confirm it is the data wanted.\n"
        f"4. If downloads are enabled: edi_download_entities(package=...{entities_arg}). It "
        "verifies checksums and never overwrites files; it refuses plans above the per-call "
        "file and byte limits, so split a large plan. Over HTTP, give the user each "
        "entity's anonymousUrl (or dataUrl, which needs a key) from edi_list_entities "
        "instead. edi_download_package fetches the whole package "
        "as one zip but needs a key and can be very large: use it only when asked.\n"
        "5. edi_get_citation for the package, and report where each file was saved."
    )


def get_prompt(name: str, arguments: Mapping[str, str] | None) -> t.GetPromptResult:
    prompt = next((p for p in PROMPTS if p.name == name), None)
    if prompt is None:
        raise ToolError(
            "not_found",
            f"Unknown prompt {name!r}.",
            details={"available": [p.name for p in PROMPTS]},
        )
    values = _validate(prompt, arguments or {})
    return t.GetPromptResult(
        description=prompt.description,
        messages=[
            t.PromptMessage(
                role="user", content=t.TextContent(type="text", text=_render(name, values))
            )
        ],
    )
