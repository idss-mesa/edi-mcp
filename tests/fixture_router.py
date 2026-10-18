"""Hermetic stand-in for PASTA, the EDI auth service, DataONE and the citation service.

Responses come from ``tests/fixtures/manifest.json``, written by
``scripts/record_fixtures.py`` from real (scrubbed) traffic. The router:

* answers the auth service itself (``POST /auth/v1/key`` and
  ``/token/refresh``) with fake JWTs for :data:`TEST_KEY`, so no real token is
  ever stored;
* enforces PASTA's credential rules: no credential -> the recorded anonymous
  403, an unknown token -> 401, a wrong ``?key=`` -> 401;
* fails the test when a credential (cookie or ``key``) reaches any other host;
* records every request in :attr:`FixtureRouter.calls`, and fails the test on
  a request it has no fixture for.
"""

from __future__ import annotations

import base64
import itertools
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode

import httpx

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = FIXTURES / "manifest.json"
TEST_KEY = "unit-test-edi-key-DO-NOT-LOG"
PASTA_HOST = "pasta.lternet.edu"
AUTH_HOST = "auth.edirepository.org"
ANONYMOUS_403 = "anon:GET pasta.lternet.edu/package/eml"
CREDENTIAL_PARAMS = {"key"}


def canonical_key(method: str, url: httpx.URL) -> str:
    """``METHOD host/raw-path?sorted-query`` without credential parameters.

    The raw (still percent-encoded) path is used so DataONE identifiers that
    embed URLs stay distinct; the recorder and the router share this function.
    """
    raw = url.raw_path.decode("ascii")
    path, _, query = raw.partition("?")
    params = sorted(
        (k, v)
        for k, v in parse_qsl(query, keep_blank_values=True)
        if k.lower() not in CREDENTIAL_PARAMS
    )
    key = f"{method.upper()} {url.host}{path}"
    return f"{key}?{urlencode(params)}" if params else key


def manifest_key(key: str, credential: bool) -> str:
    """PASTA requests recorded without a credential are kept apart as ``anon:…``."""
    on_pasta = key.split(" ", 1)[1].startswith(PASTA_HOST)
    return f"anon:{key}" if on_pasta and not credential else key


def load_manifest(path: Path = MANIFEST) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    entries = json.loads(path.read_text(encoding="utf-8"))
    return {manifest_key(e["key"], e.get("credential", False)): e for e in entries}


def fake_jwt(exp: float, serial: int) -> str:
    def b64(obj: dict[str, Any]) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'exp': exp, 'n': serial})}.sig{serial}"


@dataclass
class Reply:
    status: int = 200
    content: bytes = b""
    content_type: str = "text/plain"
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Call:
    method: str
    url: str
    host: str
    key: str
    params: dict[str, str]
    headers: dict[str, str]
    body: bytes

    @property
    def cookie(self) -> str | None:
        return self.headers.get("cookie")

    @property
    def has_credential(self) -> bool:
        return "edi-token=" in (self.cookie or "") or "key" in self.params


Responder = Reply | Callable[[Call], Reply] | type[Exception]


class FixtureRouter:
    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        import time

        self.clock = clock or time.time
        self.manifest = load_manifest()
        self.calls: list[Call] = []
        self.unexpected: list[str] = []
        self.valid_tokens: set[str] = set()
        self.token_lifetime_s = 28_800.0
        #: "ok", "down" (connection refused), "error" (HTTP 500) or "reject" (HTTP 401).
        self.auth_mode = "ok"
        #: Add PASTA's ``Set-Cookie: edi-token`` to every PASTA response (as the real one does).
        self.pasta_sets_cookie = True
        self.extra: dict[str, Responder] = {}
        self._queued: list[Responder] = []
        self._serial = itertools.count(1)

    # ---------------------------------------------------------------- configuration

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def add(self, key: str, responder: Responder) -> None:
        """Serve ``responder`` for ``canonical_key`` ``key`` (takes priority over fixtures)."""
        self.extra[key] = responder

    def inject(self, responder: Responder, times: int = 1) -> None:
        """Serve ``responder`` to the next ``times`` non-auth requests."""
        self._queued.extend([responder] * times)

    def revoke_tokens(self) -> None:
        self.valid_tokens.clear()

    def issue_token(self) -> str:
        token = fake_jwt(self.clock() + self.token_lifetime_s, next(self._serial))
        self.valid_tokens.add(token)
        return token

    # ---------------------------------------------------------------- inspection

    def calls_to(self, host: str, path_prefix: str = "") -> list[Call]:
        return [
            c
            for c in self.calls
            if c.host == host and c.key.split(" ", 1)[1].startswith(f"{host}{path_prefix}")
        ]

    def auth_calls(self, path: str = "") -> list[Call]:
        return [c for c in self.calls if c.host == AUTH_HOST and c.url.endswith(path)]

    def keys(self) -> list[str]:
        return [c.key for c in self.calls]

    # ---------------------------------------------------------------- handling

    def handle(self, request: httpx.Request) -> httpx.Response:
        call = Call(
            method=request.method,
            url=str(request.url),
            host=request.url.host,
            key=canonical_key(request.method, request.url),
            params=dict(parse_qsl(request.url.query.decode(), keep_blank_values=True)),
            headers={k.lower(): v for k, v in request.headers.items()},
            body=request.content,
        )
        self.calls.append(call)
        if call.host == AUTH_HOST:
            return self._auth(call, request)
        if call.host != PASTA_HOST and call.has_credential:
            message = f"credential sent to a non-PASTA host: {call.method} {call.host}"
            self.unexpected.append(message)
            raise AssertionError(message)
        if self._queued:
            return self._respond(self._queued.pop(0), call, request)
        if call.key in self.extra:
            return self._respond(self.extra[call.key], call, request)
        if call.host == PASTA_HOST:
            denied = self._pasta_denial(call)
            if denied is not None:
                return self._finish(denied, call)
        entry = self.manifest.get(call.key)
        if entry is None:
            message = f"unexpected upstream call: {call.key}"
            self.unexpected.append(message)
            raise AssertionError(message)
        return self._finish(self._from_entry(entry), call)

    def _from_entry(self, entry: dict[str, Any]) -> Reply:
        headers = {"location": entry["location"]} if entry.get("location") else {}
        content = (FIXTURES / entry["file"]).read_bytes() if entry.get("file") else b""
        return Reply(entry["status"], content, entry.get("contentType") or "", headers)

    def _pasta_denial(self, call: Call) -> Reply | None:
        cookie = call.cookie or ""
        if "edi-token=" in cookie:
            token = cookie.split("edi-token=", 1)[1].split(";", 1)[0]
            if token not in self.valid_tokens:
                return Reply(401, b"EDI token validation failed", "text/plain")
            return None
        if "key" in call.params:
            if call.params["key"] != TEST_KEY:
                return Reply(401, b"API key resolution failed", "text/plain")
            return None
        return self._from_entry(self.manifest[ANONYMOUS_403])

    def _auth(self, call: Call, request: httpx.Request) -> httpx.Response:
        if self.auth_mode == "down":
            raise httpx.ConnectError("connection refused", request=request)
        if self.auth_mode == "error":
            return httpx.Response(500, text="Internal Server Error")
        try:
            body = json.loads(call.body or b"{}")
        except ValueError:
            body = {}
        path = request.url.path
        if path.endswith("/key"):
            if self.auth_mode == "reject" or body.get("key") != TEST_KEY:
                return httpx.Response(401, text="API key resolution failed")
            return httpx.Response(200, json={"edi-token": self.issue_token()})
        if path.endswith("/token/refresh"):
            if body.get("edi-token") not in self.valid_tokens:
                return httpx.Response(401, text="EDI token validation failed")
            return httpx.Response(200, json={"edi-token": self.issue_token()})
        raise AssertionError(f"unexpected auth call: {call.key}")

    def _respond(self, responder: Responder, call: Call, request: httpx.Request) -> httpx.Response:
        if isinstance(responder, type) and issubclass(responder, Exception):
            raise responder("injected failure", request=request)  # type: ignore[call-arg]
        reply = responder(call) if callable(responder) else responder
        return self._finish(reply, call)

    def _finish(self, reply: Reply, call: Call) -> httpx.Response:
        headers = {"content-type": reply.content_type} if reply.content_type else {}
        headers.update(reply.headers)
        if call.host == PASTA_HOST and self.pasta_sets_cookie:
            headers["set-cookie"] = (
                f"edi-token={fake_jwt(0, 0)}; Path=/; Domain=.lternet.edu; Secure; HttpOnly"
            )
        return httpx.Response(reply.status, content=reply.content, headers=headers)


__all__ = [
    "FIXTURES",
    "Call",
    "FixtureRouter",
    "Reply",
    "canonical_key",
    "load_manifest",
    "manifest_key",
]
