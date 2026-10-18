"""EDI API key -> ``edi-token`` exchange, refresh and fallback (DESIGN.md D4).

One :class:`TokenManager` per process holds one slot per key identity, so
HTTP callers with different ``X-EDI-Key`` values never share a token. A
slot's lock makes concurrent calls exchange once. Tokens live in memory
only and are registered with the log redactor.

* No token, or an expired one: ``POST {auth}/key {"key": …}``.
* Fewer than ``token_refresh_margin_s`` seconds left: ``POST
  {auth}/token/refresh {"edi-token": …}``, falling back to a fresh exchange.
* The auth service rejects the key (4xx): ``upstream_forbidden``. A bad key
  is never downgraded to DataONE (D2).
* The auth service is unreachable or failing (network, 5xx, 429, garbage):
  the key itself is sent as ``?key=`` for ``auth_fallback_s`` seconds.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
import structlog

from edi_mcp.config import EdiConfig
from edi_mcp.edi.auth import ApiKey, jwt_expiry
from edi_mcp.errors import EdiApiError
from edi_mcp.logging import register_secret

log = structlog.get_logger("edi_mcp.auth")

TOKEN_LIFETIME_S = 28_800.0
AUTH_SERVICE = "The EDI auth service"


@dataclass(frozen=True, repr=False)
class Credential:
    """What one PASTA request carries: an ``edi-token`` cookie or the ``?key=`` parameter."""

    kind: Literal["token", "key"]
    value: str = field(repr=False)

    def __repr__(self) -> str:
        return f"Credential({self.kind}, <redacted>)"


@dataclass
class _Slot:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    token: str | None = field(default=None, repr=False)
    expires_at: float = 0.0
    fallback_until: float = 0.0
    exchanges: int = 0


class _AuthUnavailable(Exception):
    pass


class TokenManager:
    def __init__(
        self,
        http: httpx.AsyncClient,
        config: EdiConfig,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._http = http
        self._base = config.auth_base_url.rstrip("/")
        self._margin = config.token_refresh_margin_s
        self._fallback_s = config.auth_fallback_s
        self._clock = clock
        self._slots: dict[str, _Slot] = {}

    def _slot(self, key: ApiKey) -> _Slot:
        return self._slots.setdefault(key.identity(), _Slot())

    async def credential(self, key: ApiKey) -> Credential:
        """A credential for ``key``: a valid token when possible, else the key itself."""
        slot = self._slot(key)
        async with slot.lock:
            now = self._clock()
            if slot.token and slot.expires_at - now > self._margin:
                return Credential("token", slot.token)
            if slot.fallback_until > now:
                return Credential("key", key.value)
            try:
                token = None
                if slot.token and slot.expires_at - now > 30:
                    try:
                        token = await self._post("/token/refresh", {"edi-token": slot.token})
                    except EdiApiError:
                        token = None
                if token is None:
                    slot.exchanges += 1
                    token = await self._post("/key", {"key": key.value})
            except _AuthUnavailable as exc:
                slot.token = None
                slot.fallback_until = now + self._fallback_s
                log.warning("auth.fallback_to_key_param", reason=str(exc))
                return Credential("key", key.value)
            slot.token = token
            slot.expires_at = jwt_expiry(token) or now + TOKEN_LIFETIME_S
            slot.fallback_until = 0.0
            return Credential("token", token)

    def invalidate(self, key: ApiKey, token: str) -> None:
        """Forget ``token`` (PASTA answered 401 to it); the next call exchanges again."""
        slot = self._slot(key)
        if slot.token == token:
            slot.token = None
            slot.expires_at = 0.0

    def exchanges(self, key: ApiKey) -> int:
        return self._slot(key).exchanges

    async def _post(self, path: str, body: dict[str, Any]) -> str:
        try:
            response = await self._http.post(
                f"{self._base}{path}",
                json=body,
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise _AuthUnavailable(type(exc).__name__) from None
        status = response.status_code
        if status >= 500 or status == 429:
            raise _AuthUnavailable(f"HTTP {status}")
        if status >= 400:
            raise EdiApiError(
                401,
                f"EDI did not accept the API key (HTTP {status} from {path}).",
                f"/auth/v1{path}",
                credential_sent=True,
                service=AUTH_SERVICE,
            )
        try:
            token = response.json().get("edi-token")
        except (ValueError, AttributeError):
            token = None
        if not isinstance(token, str) or not token:
            raise _AuthUnavailable("response carried no edi-token")
        register_secret(token)
        return token


__all__ = ["Credential", "TokenManager"]
