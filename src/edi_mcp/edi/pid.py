"""EDI package identifier parsing (DESIGN.md D9).

Agents paste whatever they found, so :func:`parse_reference` accepts:

* ``scope.identifier.revision`` / ``scope/identifier/revision`` (revision
  optional, or ``newest`` / ``oldest``), with an optional ``.xml`` suffix as
  in DataONE file names;
* EDI DOIs: ``doi:10.6073/pasta/<md5>``, ``10.6073/pasta/<md5>`` and
  ``https://doi.org/…`` / ``dx.doi.org`` URLs;
* portal URLs: ``…/nis/mapbrowse?scope=&identifier=&revision=`` or
  ``…?packageid=scope.id.rev``;
* PASTA URLs (``/package/<service>/eml/scope/id/rev[/entityId]``), also when
  URL-encoded inside a DataONE ``/object/`` or ``/resolve/`` URL.

Parsing is offline. Turning a DOI or a missing/``newest``/``oldest`` revision
into a concrete package needs a backend (:mod:`edi_mcp.edi.backends`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, unquote, urlsplit

from edi_mcp.errors import ToolError

RevisionSpec = int | Literal["newest", "oldest"] | None

GUIDE = "edi://guide/package-identifiers"
DOI_PREFIX = "10.6073/pasta/"
_SCOPE = r"[A-Za-z][A-Za-z0-9_-]*"
_PACKAGE_RE = re.compile(
    rf"^(?P<scope>{_SCOPE})[./](?P<identifier>\d+)(?:[./](?P<revision>\d+|newest|oldest))?$",
    re.IGNORECASE,
)
_DOI_RE = re.compile(r"(?:^|doi:|doi\.org/)10\.6073/pasta/(?P<md5>[0-9a-f]{32})$", re.IGNORECASE)
_ANY_DOI_RE = re.compile(r"(?:^|doi:|doi\.org/)(10\.\d{4,9}/\S+)$", re.IGNORECASE)
_PASTA_PATH_RE = re.compile(
    rf"/package/(?:[a-z]+/)*eml/(?P<scope>{_SCOPE})/(?P<identifier>\d+)"
    r"(?:/(?P<revision>\d+|newest|oldest))?(?:/(?P<entity>[0-9a-f]{32}))?/?$",
    re.IGNORECASE,
)
ACCEPTED_FORMS = [
    "knb-lter-hbr.14.22",
    "knb-lter-hbr/14/22",
    "knb-lter-hbr.14 (with revision='newest')",
    "doi:10.6073/pasta/<md5>",
    "https://doi.org/10.6073/pasta/<md5>",
    "https://portal.edirepository.org/nis/mapbrowse?scope=…&identifier=…&revision=…",
    "https://pasta.lternet.edu/package/metadata/eml/<scope>/<id>/<rev>",
]


@dataclass(frozen=True)
class PackageId:
    scope: str
    identifier: int
    revision: int | None = None

    def __post_init__(self) -> None:
        if self.identifier < 0 or (self.revision is not None and self.revision < 0):
            raise ValueError("identifier and revision must be non-negative")

    @property
    def series(self) -> str:
        """``scope.identifier`` (all revisions)."""
        return f"{self.scope}.{self.identifier}"

    @property
    def package_id(self) -> str:
        """``scope.identifier.revision``; requires a revision."""
        if self.revision is None:
            raise ValueError(f"{self.series} has no revision")
        return f"{self.series}.{self.revision}"

    @property
    def path(self) -> str:
        """``scope/identifier[/revision]`` as used in PASTA paths."""
        base = f"{self.scope}/{self.identifier}"
        return base if self.revision is None else f"{base}/{self.revision}"

    def with_revision(self, revision: int) -> PackageId:
        return PackageId(self.scope, self.identifier, revision)

    def __str__(self) -> str:
        return self.package_id if self.revision is not None else self.series


@dataclass(frozen=True)
class Doi:
    """An EDI DOI; ``md5`` is lower-case hex."""

    md5: str

    @property
    def doi(self) -> str:
        return f"{DOI_PREFIX}{self.md5}"

    @property
    def pid(self) -> str:
        """The DataONE identifier of the package's resource map."""
        return f"doi:{self.doi}"

    @property
    def url(self) -> str:
        return f"https://doi.org/{self.doi}"


@dataclass(frozen=True)
class PackageRef:
    """A parsed reference: a package (revision maybe unresolved) or a DOI."""

    raw: str
    package: PackageId | None = None
    revision: RevisionSpec = None
    doi: Doi | None = None
    entity_id: str | None = None
    form: str = "package-id"

    @property
    def needs_backend(self) -> bool:
        return self.doi is not None or not isinstance(self.revision, int)


def _invalid(value: str, why: str) -> ToolError:
    return ToolError(
        "invalid_argument",
        f"{value!r} is not an EDI package identifier: {why}",
        details={"value": value[:200], "accepted": ACCEPTED_FORMS},
        hint=f"Read {GUIDE}.",
    )


def _revision(token: str | None) -> RevisionSpec:
    if token is None:
        return None
    lowered = token.lower()
    if lowered in ("newest", "oldest"):
        return lowered  # type: ignore[return-value]
    return int(token)


def _from_match(raw: str, m: re.Match[str], form: str, entity: str | None = None) -> PackageRef:
    revision = _revision(m.group("revision"))
    package = PackageId(
        m.group("scope"),
        int(m.group("identifier")),
        revision if isinstance(revision, int) else None,
    )
    return PackageRef(
        raw=raw,
        package=package,
        revision=revision,
        entity_id=entity.lower() if entity else None,
        form=form,
    )


def _from_url(raw: str, text: str) -> PackageRef | None:
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    path = unquote(parts.path)
    if host in ("doi.org", "dx.doi.org"):
        return _from_doi(raw, f"doi.org{path}")
    query = {k.lower(): v[0] for k, v in parse_qs(parts.query).items() if v}
    if "packageid" in query:
        m = _PACKAGE_RE.match(query["packageid"].strip())
        if m:
            return _from_match(raw, m, "portal-url")
    if "scope" in query and "identifier" in query:
        candidate = f"{query['scope']}.{query['identifier']}"
        if query.get("revision"):
            candidate += f".{query['revision']}"
        m = _PACKAGE_RE.match(candidate.strip())
        if m:
            return _from_match(raw, m, "portal-url")
    # A PASTA URL, possibly URL-encoded inside a DataONE /object/ or /resolve/ URL.
    inner = re.search(r"https?://[^/]+(/package/.*)$", path)
    pasta_path = inner.group(1) if inner else path
    m = _PASTA_PATH_RE.search(pasta_path)
    if m:
        return _from_match(raw, m, "pasta-url", m.group("entity"))
    inner_doi = re.search(r"(doi:10\.6073/pasta/[0-9a-f]{32})$", path, re.IGNORECASE)
    if inner_doi:
        return _from_doi(raw, inner_doi.group(1))
    return None


def _from_doi(raw: str, text: str) -> PackageRef | None:
    m = _DOI_RE.search(text)
    if m:
        return PackageRef(raw=raw, doi=Doi(m.group("md5").lower()), form="doi")
    if _ANY_DOI_RE.search(text):
        raise _invalid(raw, "only EDI DOIs (10.6073/pasta/…) identify EDI packages")
    return None


def parse_reference(value: str, revision: RevisionSpec = None) -> PackageRef:
    """Parse any accepted identifier form; ``revision`` fills in a missing revision.

    An explicit revision in ``value`` wins over ``revision``; a mismatch is an
    error rather than a silent choice.
    """
    raw = value
    text = value.strip()
    if not text:
        raise _invalid(raw, "it is empty")
    if text.lower().endswith(".xml"):
        text = text[:-4]
    ref: PackageRef | None
    if re.match(r"^https?://", text, re.IGNORECASE):
        ref = _from_url(raw, text)
    elif text.lower().startswith("doi:") or text.startswith("10."):
        ref = _from_doi(raw, text)
    else:
        m = _PACKAGE_RE.match(text)
        ref = _from_match(raw, m, "package-id") if m else None
    if ref is None:
        raise _invalid(raw, "expected scope.identifier.revision, an EDI DOI or an EDI/PASTA URL")
    if revision is not None and ref.doi is None:
        if ref.revision is not None and ref.revision != revision:
            raise ToolError(
                "invalid_argument",
                f"{raw!r} names revision {ref.revision} but revision={revision!r} was also given.",
                details={"value": raw[:200], "revision": revision},
                hint="Pass the revision in one place only.",
            )
        if ref.revision is None and ref.package is not None:
            fixed = revision if isinstance(revision, int) else None
            ref = PackageRef(
                raw=raw,
                package=PackageId(ref.package.scope, ref.package.identifier, fixed),
                revision=revision,
                entity_id=ref.entity_id,
                form=ref.form,
            )
    return ref


__all__ = ["ACCEPTED_FORMS", "Doi", "PackageId", "PackageRef", "RevisionSpec", "parse_reference"]
