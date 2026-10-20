#!/usr/bin/env python3
"""Maintainer tool for the hermetic fixtures in ``tests/fixtures/``.

    uv run python scripts/record_fixtures.py check     # CI: the rules below
    set -a; . ./.env; set +a
    uv run python scripts/record_fixtures.py record    # re-record everything live

``record`` drives the real backends (PASTA with ``EDI_API_KEY``, DataONE
without) through a recording transport, so fixtures match the exact requests
edi-mcp makes. It never records auth-service traffic (that is where tokens
live; the test router fakes it), stores no response headers except
``Content-Type`` and ``Location``, and scrubs every body *before* it is
written: the API key, every ``edi-token`` it saw, anything JWT-shaped, and
the identity claims (``sub``, ``cn``, ``email``, non-system principals)
decoded from the token. Recordings land in ``tests/fixtures/_raw/``
(gitignored) and replace the committed set only if ``check`` passes on them.

Rules checked: no JWT-shaped string, no ``edi-token=``, no ``set-cookie``, no
``key=`` in a manifest URL, no API key (when ``EDI_API_KEY`` is set), every
manifest file present, each fixture <= 40 KB, total <= 3 MB.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fixture_router import (  # noqa: E402
    ANONYMOUS_403,
    canonical_key,
    load_manifest,
    manifest_key,
)

FIXTURES = ROOT / "tests" / "fixtures"
RAW = FIXTURES / "_raw"
MAX_FIXTURE_BYTES = 40 * 1024
MAX_TOTAL_BYTES = 3 * 1024 * 1024
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{6,}(?:\.[A-Za-z0-9_-]*){0,2}")
FORBIDDEN_RE = re.compile(r"edi-token=|set-cookie", re.IGNORECASE)
KEY_PARAM_RE = re.compile(r"[?&]key=", re.IGNORECASE)
SYSTEM_PRINCIPALS = {"public access", "human access", "authenticated access"}
#: Any EDI user principal: PASTA's change and upload feeds name other uploaders.
PRINCIPAL_RE = re.compile(r"EDI-[0-9a-f]{40}")
EXTENSIONS = {
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/rdf+xml": ".xml",
    "application/json": ".json",
    "text/csv": ".csv",
}


# ---------------------------------------------------------------------- scrubbing


class Scrubber:
    """Replaces known secrets and identity strings, and anything JWT-shaped."""

    def __init__(self, secrets: Iterable[str] = ()) -> None:
        self.secrets: set[str] = {s for s in secrets if s and len(s) >= 4}

    def add(self, *values: str | None) -> None:
        for value in values:
            if value and len(value) >= 4:
                self.secrets.add(value)

    def add_token_claims(self, token: str) -> None:
        """Register the token and the identity strings its payload carries."""
        self.add(token)
        try:
            payload = token.split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except (IndexError, ValueError, binascii.Error):
            return
        if not isinstance(claims, dict):
            return
        for name in ("sub", "cn", "email", "givenName", "surName"):
            value = claims.get(name)
            if isinstance(value, str):
                self.add(value)
        for principal in claims.get("principals") or []:
            if isinstance(principal, str) and principal.lower() not in SYSTEM_PRINCIPALS:
                self.add(principal)

    def scrub(self, text: str) -> str:
        for secret in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(secret, "REDACTED")
        text = PRINCIPAL_RE.sub("EDI-REDACTED", text)
        return JWT_RE.sub("REDACTED-JWT", text)

    def leaks(self, text: str) -> list[str]:
        problems = []
        if JWT_RE.search(text):
            problems.append("JWT-shaped string")
        if FORBIDDEN_RE.search(text):
            problems.append("edi-token or set-cookie")
        if PRINCIPAL_RE.search(text):
            problems.append("EDI user principal")
        problems.extend(f"secret #{i}" for i, s in enumerate(sorted(self.secrets)) if s in text)
        return problems


# ---------------------------------------------------------------------- check


def check(directory: Path = FIXTURES, scrubber: Scrubber | None = None) -> list[str]:
    scrubber = scrubber or Scrubber([os.environ.get("EDI_API_KEY", "")])
    problems: list[str] = []
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return [f"{manifest_path.name}: missing"]
    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    if ANONYMOUS_403 not in load_manifest(manifest_path):
        problems.append("manifest: the anonymous PASTA 403 fixture is missing")
    referenced = set()
    for entry in entries:
        if KEY_PARAM_RE.search(entry["key"]):
            problems.append(f"manifest: credential parameter in {entry['key'][:60]}")
        if entry.get("file"):
            referenced.add(entry["file"])
            if not (directory / entry["file"]).exists():
                problems.append(f"manifest: {entry['file']} is missing")
    total = 0
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        if "_raw" in path.relative_to(directory).parts and directory == FIXTURES:
            continue
        size = path.stat().st_size
        total += size
        name = str(path.relative_to(directory))
        if size > MAX_FIXTURE_BYTES:
            problems.append(f"{name}: {size} bytes > {MAX_FIXTURE_BYTES}")
        text = path.read_text(encoding="utf-8", errors="replace")
        problems.extend(f"{name}: {leak}" for leak in scrubber.leaks(text))
        if path.name != "manifest.json" and name not in referenced:
            problems.append(f"{name}: not referenced by the manifest")
    if total > MAX_TOTAL_BYTES:
        problems.append(f"fixtures total {total} bytes > {MAX_TOTAL_BYTES}")
    return problems


# ---------------------------------------------------------------------- recording


def fixture_name(key: str, status: int, content_type: str | None) -> str:
    """``<host label>/<readable path slug>_<status>_<hash>.<ext>``."""
    rest = key.split(" ", 1)[1]
    host, _, path = rest.partition("/")
    readable = unquote(unquote(path.split("?", 1)[0]))
    readable = re.sub(r"^.*?pasta\.lternet\.edu/package/", "", readable)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", readable).strip("_")[-60:]
    digest = hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:8]
    ext = EXTENSIONS.get((content_type or "").split(";")[0], ".txt")
    return f"{host.split('.')[0] or 'other'}/{slug or 'root'}_{status}_{digest}{ext}"


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport, scrubber: Scrubber, out: Path) -> None:
        self.inner = inner
        self.scrubber = scrubber
        self.out = out
        self.entries: dict[str, dict[str, Any]] = {}

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.inner.handle_async_request(request)
        decoded = await response.aread()  # already content-decoded by httpx
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
        }
        replay = httpx.Response(
            response.status_code, headers=headers, content=decoded, request=request
        )
        host = request.url.host
        if host == "auth.edirepository.org":
            try:
                token = json.loads(decoded).get("edi-token")
            except (ValueError, AttributeError):
                token = None
            if isinstance(token, str):
                self.scrubber.add_token_claims(token)
            return replay  # never recorded
        key = canonical_key(request.method, request.url)
        content_type = (response.headers.get("content-type") or "").split(";")[0] or None
        entry: dict[str, Any] = {
            "key": key,
            "status": response.status_code,
            "contentType": content_type,
            "credential": "edi-token=" in request.headers.get("cookie", "")
            or "key" in dict(request.url.params),
        }
        if response.headers.get("location"):
            entry["location"] = self.scrubber.scrub(response.headers["location"])
        if decoded:
            name = fixture_name(
                manifest_key(key, entry["credential"]), response.status_code, content_type
            )
            path = self.out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                self.scrubber.scrub(decoded.decode("utf-8", "replace")), encoding="utf-8"
            )
            entry["file"] = name
        self.entries[manifest_key(key, entry["credential"])] = entry
        return replay

    def rescrub(self) -> None:
        """Second pass: identity strings learnt from a later token reach earlier files too."""
        for path in self.out.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                clean = self.scrubber.scrub(text)
                if clean != text:
                    path.write_text(clean, encoding="utf-8")

    def write_manifest(self) -> None:
        entries = [self.entries[k] for k in sorted(self.entries)]
        (self.out / "manifest.json").write_text(
            json.dumps(entries, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
        )


async def _scenarios(transport: RecordingTransport, key_value: str) -> None:
    from pydantic import SecretStr

    from edi_mcp.config import Config
    from edi_mcp.context import UpstreamStats
    from edi_mcp.edi.auth import ApiKey
    from edi_mcp.edi.backends import DataOneBackend, PastaBackend, SearchQuery
    from edi_mcp.edi.backends.dataone import SOURCE_FILTER
    from edi_mcp.edi.client import EdiClient
    from edi_mcp.edi.pid import Doi, PackageId
    from edi_mcp.errors import EdiApiError, ToolError
    from edi_mcp.server import create_server

    config = Config.model_validate({})
    config.edi.api_key = SecretStr(key_value)
    config.cache.enabled = False
    # Download scenarios write here, never into the recorder's real download directory.
    config.downloads.directory = Path(tempfile.mkdtemp(prefix="edi-mcp-record-"))
    client = EdiClient(config.edi, config.cache, http_transport=transport)
    key = ApiKey(key_value, "config")
    hbr = PackageId("knb-lter-hbr", 14, 22)
    edi_pkg = PackageId("edi", 2081, 1)
    hbr_doi = Doi("2017345f0977c0f7c46e1ad90ce1b062")  # knb-lter-hbr.14.22
    old_doi = Doi("cb5f623deb94bdefc7502655b03f6645")  # knb-lter-hbr.14.21 (superseded)

    def pasta() -> PastaBackend:
        backend = PastaBackend(client, config, UpstreamStats(), key)
        backend.set_fallback(DataOneBackend(client, config, UpstreamStats()))
        return backend

    def dataone() -> DataOneBackend:
        return DataOneBackend(client, config, UpstreamStats())

    steps: list[tuple[str, Callable[[], Any]]] = [
        ("anonymous PASTA 403", lambda: client.get(f"{config.edi.pasta_base_url}/package/eml")),
        ("pasta scopes", lambda: pasta().list_scopes()),
        ("pasta identifiers", lambda: pasta().list_identifiers("knb-lter-hbr")),
        ("pasta revisions", lambda: pasta().list_revisions("knb-lter-hbr", 14)),
        ("pasta revisions 404", lambda: pasta().list_revisions("knb-lter-hbr", 999999)),
        ("pasta eml", lambda: pasta().read_eml(hbr)),
        ("pasta eml 404", lambda: pasta().read_eml(PackageId("knb-lter-hbr", 2, 999))),
        ("pasta entities", lambda: pasta().list_entities(hbr)),
        (
            "pasta checksum",
            lambda: pasta().entity_checksum(hbr, "c4f72fa0cb155f1b61f1333bb67e3d00"),
        ),
        ("pasta doi", lambda: pasta().package_doi(hbr)),
        ("pasta search", lambda: pasta().search(SearchQuery(text="streamflow", limit=5))),
        (
            "pasta search scope",
            lambda: pasta().search(
                SearchQuery(text="precipitation", scope="knb-lter-hbr", limit=3)
            ),
        ),
        ("pasta resolve doi", lambda: pasta().resolve_doi(hbr_doi)),
        ("pasta resolve old doi", lambda: pasta().resolve_doi(old_doi)),
        (
            "dataone ping",
            lambda: client.get(
                f"{config.edi.dataone_cn_url}/query/solr/",
                {"q": "*:*", "fq": SOURCE_FILTER, "rows": "0", "wt": "json"},
            ),
        ),
        ("dataone search", lambda: dataone().search(SearchQuery(text="streamflow", limit=5))),
        (
            "dataone search scope",
            lambda: dataone().search(
                SearchQuery(text="precipitation", scope="knb-lter-hbr", limit=3)
            ),
        ),
        ("dataone identifiers", lambda: dataone().list_identifiers("knb-lter-hbr")),
        ("dataone identifiers none", lambda: dataone().list_identifiers("no-such-scope")),
        ("dataone revisions", lambda: dataone().list_revisions("knb-lter-hbr", 14)),
        ("dataone eml", lambda: dataone().read_eml(hbr)),
        ("dataone eml edi", lambda: dataone().read_eml(edi_pkg)),
        ("dataone eml 404", lambda: dataone().read_eml(PackageId("knb-lter-hbr", 2, 20))),
        ("dataone entities", lambda: dataone().list_entities(hbr)),
        ("dataone entities edi", lambda: dataone().list_entities(edi_pkg)),
        (
            "dataone checksum",
            lambda: dataone().entity_checksum(hbr, "c4f72fa0cb155f1b61f1333bb67e3d00"),
        ),
        ("dataone doi", lambda: dataone().package_doi(hbr)),
        ("dataone doi edi", lambda: dataone().package_doi(edi_pkg)),
        # DataONE has indexed hbr.14.22 since 2026-10-19; record the citation fallback directly.
        ("dataone doi via cite", lambda: dataone()._doi_from_citation(hbr)),
        ("dataone resolve doi", lambda: dataone().resolve_doi(hbr_doi)),
    ]
    # Tool-level scenarios: the exact requests the tool tests make, on both backends.
    anon_config = config.model_copy(deep=True)
    anon_config.edi.api_key = None
    servers = {
        "key": create_server(config, transport="stdio", http_transport=transport),
        "anon": create_server(anon_config, transport="stdio", http_transport=transport),
    }

    def tool(who: str, name: str, args: dict[str, Any], ok: bool = True) -> Callable[[], Any]:
        async def run() -> str:
            outcome = await servers[who].call(name, args)
            if outcome.is_error == ok:
                raise RuntimeError(f"{who} {name}({args}) unexpectedly {outcome.payload}")
            if outcome.is_error:
                return f"error {outcome.payload['error']['code']}"
            page = outcome.payload.get("page") or {}
            return f"ok returned={page.get('returned')} total={page.get('total')}"

        return run

    for who, name, args, ok in TOOL_SCENARIOS:
        steps.append(
            (f"{who} {name.removeprefix('edi_')} {next(iter(args), '')}", tool(who, name, args, ok))
        )
    try:
        for label, step in steps:
            try:
                result = await step()
                summary = (
                    f"{len(result)} items" if isinstance(result, (list, bytes)) else repr(result)
                )
            except (EdiApiError, ToolError) as exc:
                summary = f"error {type(exc).__name__}: {getattr(exc, 'code', '')}"
            print(f"  {label:28} {transport.scrubber.scrub(summary)[:90]}")
    finally:
        await client.aclose()
        for server in servers.values():
            await server.aclose()


#: (backend, tool, arguments, succeeds) recorded through the real tools.
TOOL_SCENARIOS: list[tuple[str, str, dict[str, Any], bool]] = [
    *(
        (who, "edi_search_packages", args, True)
        for who in ("key", "anon")
        for args in (
            {
                "author": "likens",
                "start_year": 1960,
                "end_year": 1970,
                "sort": "newest",
                "limit": 5,
            },
            {"bbox": [-107, 32.4, -106.5, 32.8], "limit": 5},
        )
    ),
    ("anon", "edi_search_packages", {"query": "thiessen", "scope": "HBR", "limit": 3}, True),
    ("anon", "edi_search_packages", {"scope": "icarus", "limit": 3}, True),
    ("key", "edi_list_identifiers", {"scope": "knb-lter-zzz"}, False),
    ("key", "edi_list_revisions", {"package": "jrn.210548103"}, True),
    ("anon", "edi_list_revisions", {"package": "jrn.210548103"}, True),
    # Step 5: packages, metadata, entities. jrn.210548103.32 is pinned because DataONE's
    # newest revision lags PASTA's (33 on 2026-10-19).
    *(
        (who, name, args, True)
        for who in ("key", "anon")
        for name, args in (
            ("edi_get_package", {"package": "knb-lter-hbr.14.22"}),
            ("edi_get_metadata", {"package": "knb-lter-jrn.210548103.32"}),
            ("edi_get_metadata", {"package": "edi.2081.1", "include": ["rights"]}),
            (
                "edi_list_entities",
                {"package": "knb-lter-jrn.210548103.32", "include_checksums": True},
            ),
            ("edi_list_entities", {"package": "knb-lter-hbr.14.22", "entity": "thiessen_weights"}),
        )
    ),
    ("key", "edi_get_package", {"package": "knb-lter-hbr.14"}, True),
    ("key", "edi_get_package", {"package": "icarus.13.1"}, False),
    # Step 6. thiessen_weights (734 bytes) is the preview/download entity; edi.2081.1's
    # quality report (22 KB) fits the fixture cap, hbr.14.22's (83 KB) does not.
    *(
        (who, name, args, True)
        for who in ("key", "anon")
        for name, args in (
            (
                "edi_preview_entity",
                {"package": "knb-lter-hbr.14.22", "entity": "thiessen_weights", "rows": 5},
            ),
            ("edi_get_citation", {"package": "knb-lter-hbr.14.22"}),
            ("edi_get_citation", {"package": "knb-lter-hbr.14.22", "style": "BIBTEX"}),
            ("edi_get_quality_report", {"package": "edi.2081.1"}),
            (
                "edi_download_entities",
                {
                    "package": "knb-lter-hbr.14.22",
                    "entities": ["thiessen_weights"],
                    "dest_subdir": who,
                },
            ),
        )
    ),
    ("anon", "edi_get_citation", {"package": "icarus.13.1"}, False),
    ("key", "edi_get_lineage", {"package": "knb-lter-hbr.14.22"}, True),
    (
        "key",
        "edi_recent_changes",
        {"from_date": "2026-10-12", "to_date": "2026-10-18", "scope": "edi"},
        True,
    ),
    ("key", "edi_get_read_counts", {"package": "edi.2081"}, True),
    ("key", "edi_get_read_counts", {"package": "knb-lter-jrn.210548103.32"}, True),
]


def record() -> int:
    key_value = os.environ.get("EDI_API_KEY", "").strip()
    if not key_value:
        print("EDI_API_KEY is not set (set -a; . ./.env; set +a)", file=sys.stderr)
        return 2
    scrubber = Scrubber([key_value])
    if RAW.exists():
        shutil.rmtree(RAW)
    RAW.mkdir(parents=True)
    transport = RecordingTransport(httpx.AsyncHTTPTransport(), scrubber, RAW)
    print("recording:")
    asyncio.run(_scenarios(transport, key_value))
    transport.write_manifest()
    transport.rescrub()
    problems = check(RAW, scrubber)
    if problems:
        for problem in problems:
            print("FIXTURE:", problem)
        print(f"{len(problems)} problem(s); recordings left in {RAW} and NOT promoted")
        return 1
    for child in FIXTURES.iterdir():
        if child.name != "_raw":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    for child in RAW.iterdir():
        shutil.move(str(child), FIXTURES / child.name)
    RAW.rmdir()
    print(f"promoted {len(transport.entries)} recordings to {FIXTURES}")
    return 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "check":
        problems = check()
        for problem in problems:
            print("FIXTURE:", problem)
        print(f"{len(problems)} problem(s)")
        return 1 if problems else 0
    if argv[0] == "record":
        return record()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
