"""The scope snapshot and tolerant scope resolution (DESIGN.md D9).

``resources_static/scopes.json`` lists every scope PASTA served on its
``asOf`` date with a name (where one is verified), kind, LTER site code,
location and package counts on both backends. It is the
``edi://reference/scopes`` resource, the keyless answer of
``edi_list_scopes``, and the vocabulary for resolving scope inputs:

1. an exact scope (``knb-lter-jrn``) passes as is;
2. a three-letter LTER site code (``JRN``, ``jrn``) maps to ``knb-lter-<code>``
   (so ``cap`` is Central Arizona-Phoenix; ``msb-cap`` needs its exact code);
3. anything else is scored against names, aliases and locations (a location
   counts like a name, so "Alaska" is ambiguous across four sites) with
   neon-mcp's thresholds: accepted at score >= 0.75 and >= 1.15 x the
   runner-up, echoed in ``resolved``; otherwise ``ambiguous_input`` (ranked
   candidates) or ``not_found`` (``didYouMean``);
4. a hyphenated scope code missing from the snapshot, or a one-word code
   that matches nothing, passes through unchanged, so scopes newer than the
   snapshot keep working (the backend then decides).
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from edi_mcp.edi.pid import PackageRef, RevisionSpec, parse_reference
from edi_mcp.errors import ToolError
from edi_mcp.models.common import Resolved

SCOPES_FILE = Path(__file__).resolve().parent.parent / "resources_static" / "scopes.json"
ScopeKind = Literal["lter", "edi", "bulk", "project", "agency", "other"]

ACCEPT_SCORE = 0.75
ACCEPT_MARGIN = 1.15
NOT_FOUND_BELOW = 0.45
MAX_CANDIDATES = 8
SCOPE_CODE_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_WORD_RE = re.compile(r"[a-z0-9]+")
#: ``<scope name>.<identifier>[.<revision>]`` where the name is not a scope code.
_NAMED_PACKAGE_RE = re.compile(
    r"^(?P<name>[^./]+?)\s*[./]\s*(?P<identifier>\d+)(?:[./](?P<revision>\d+|newest|oldest))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScopeRecord:
    scope: str
    name: str | None
    kind: ScopeKind
    site_code: str | None
    location: str | None
    aliases: tuple[str, ...]
    pasta_packages: int
    dataone_packages: int

    @property
    def dataone_replicated(self) -> bool:
        return self.dataone_packages > 0


@dataclass(frozen=True)
class ScopeSnapshot:
    as_of: str
    records: tuple[ScopeRecord, ...]

    def get(self, scope: str) -> ScopeRecord | None:
        return next((r for r in self.records if r.scope == scope), None)

    def by_site_code(self, code: str) -> ScopeRecord | None:
        upper = code.upper()
        return next((r for r in self.records if r.site_code == upper), None)


@dataclass(frozen=True)
class Candidate:
    scope: str
    label: str
    score: float


@lru_cache(maxsize=1)
def load_scopes() -> ScopeSnapshot:
    raw: dict[str, Any] = json.loads(SCOPES_FILE.read_text(encoding="utf-8"))
    records = tuple(
        ScopeRecord(
            scope=r["scope"],
            name=r.get("name"),
            kind=r["kind"],
            site_code=r.get("siteCode"),
            location=r.get("location"),
            aliases=tuple(r.get("aliases") or ()),
            pasta_packages=int(r.get("pastaPackages") or 0),
            dataone_packages=int(r.get("dataonePackages") or 0),
        )
        for r in raw["scopes"]
    )
    return ScopeSnapshot(as_of=str(raw["asOf"]), records=records)


# ---------------------------------------------------------------------------
# Scoring (neon-mcp's word-coverage scorer)
# ---------------------------------------------------------------------------


def words(text: str | None) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def _word_hit(word: str, vocab: set[str]) -> bool:
    return word in vocab or any(
        difflib.SequenceMatcher(None, word, v).ratio() >= 0.85 for v in vocab
    )


def name_score(query: str, name: str) -> float:
    """0..1 similarity driven by word coverage: every query word must be accounted for
    before a score can reach the 0.75 acceptance threshold."""
    q_words, n_words = words(query), words(name)
    if not q_words or not n_words:
        return 0.0
    q, n = " ".join(q_words), " ".join(n_words)
    if q == n:
        return 1.0
    if f" {q} " in f" {n} ":
        return 0.95 if n.startswith(q) else 0.9
    vocab = set(n_words)
    hits = sum(1 for w in q_words if _word_hit(w, vocab))
    if hits == len(q_words):
        return 0.85
    return round(0.3 + 0.3 * hits / len(q_words), 3)


def _record_score(text: str, record: ScopeRecord) -> float:
    # The location scores like a name, so "Alaska" ties the four Alaska sites
    # (ambiguous_input) instead of picking the one whose name says Alaska.
    names = [n for n in (record.name, *record.aliases, record.location) if n]
    if not record.name or not names:
        return 0.0
    return max(name_score(text, n) for n in names)


def candidates(text: str, snapshot: ScopeSnapshot, n: int = MAX_CANDIDATES) -> list[Candidate]:
    scored = [
        Candidate(r.scope, r.name or r.scope, round(_record_score(text, r), 3))
        for r in snapshot.records
    ]
    scored = [c for c in scored if c.score > 0.3]
    scored.sort(key=lambda c: (-c.score, c.scope))
    return scored[:n]


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_scope(value: str, *, field: str = "scope") -> tuple[str, Resolved | None]:
    """A scope for ``value``: an exact scope, an LTER site code, or a name/location."""
    text = value.strip()
    lower = text.lower()
    snapshot = load_scopes()
    if snapshot.get(lower) is not None:
        return lower, None
    record = snapshot.by_site_code(lower) if len(lower) == 3 else None
    if record is not None:
        return record.scope, Resolved(field=field, input=text, code=record.scope, confidence=1.0)
    if "-" in text and SCOPE_CODE_RE.match(text):
        # A scope code missing from the snapshot may be newer; the backend decides.
        return text, None
    ranked = candidates(text, snapshot)
    top = ranked[0] if ranked else None
    if (top is None or top.score < NOT_FOUND_BELOW) and SCOPE_CODE_RE.match(text):
        return text, None
    if top is None or top.score < NOT_FOUND_BELOW:
        raise ToolError(
            "not_found",
            f"No EDI scope matches {text!r}.",
            details={
                "field": field,
                "input": text,
                "didYouMean": [{"scope": c.scope, "name": c.label} for c in ranked[:3]],
            },
            hint="Call edi_list_scopes, or pass an exact scope such as knb-lter-jrn.",
        )
    runner = ranked[1].score if len(ranked) > 1 else 0.0
    exact = top.score >= 1.0 and runner < 1.0
    if exact or (
        top.score >= ACCEPT_SCORE and (runner == 0.0 or top.score >= ACCEPT_MARGIN * runner)
    ):
        return top.scope, Resolved(
            field=field, input=text, code=top.scope, confidence=round(top.score, 2)
        )
    raise ToolError(
        "ambiguous_input",
        f"{text!r} matches several EDI scopes; call again with one of the candidate scopes.",
        details={
            "field": field,
            "input": text,
            "candidates": [{"scope": c.scope, "name": c.label, "score": c.score} for c in ranked],
        },
    )


def resolve_reference(
    value: str, revision: RevisionSpec = None, *, field: str = "package"
) -> tuple[PackageRef, list[Resolved]]:
    """:func:`parse_reference`, also accepting a site code or scope name in place of the
    scope (``jrn.210548103``, ``Jornada Basin.210548103.43``)."""
    try:
        ref = parse_reference(value, revision)
    except ToolError as err:
        m = _NAMED_PACKAGE_RE.match(value.strip())
        if m is None or err.code != "invalid_argument":
            raise
        scope, res = resolve_scope(m.group("name"), field=field)
        text = f"{scope}.{m.group('identifier')}"
        if m.group("revision"):
            text += f".{m.group('revision')}"
        ref = replace(parse_reference(text, revision), raw=value)
        return ref, [res] if res else []
    if ref.package is None or load_scopes().get(ref.package.scope) is not None:
        return ref, []
    scope, res = resolve_scope(ref.package.scope, field=field)
    if scope == ref.package.scope:
        return ref, []
    return replace(ref, package=replace(ref.package, scope=scope)), [res] if res else []


__all__ = [
    "ACCEPT_MARGIN",
    "ACCEPT_SCORE",
    "SCOPE_CODE_RE",
    "Candidate",
    "ScopeRecord",
    "ScopeSnapshot",
    "candidates",
    "load_scopes",
    "name_score",
    "resolve_reference",
    "resolve_scope",
]
