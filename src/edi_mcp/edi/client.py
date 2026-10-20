"""The upstream HTTP client shared by both backends.

One :class:`EdiClient` per process wraps one ``httpx.AsyncClient`` and a
:class:`TokenManager`. Rules (DESIGN.md D4, CLAUDE.md security rules):

* Credentials go to the PASTA host only, per request: ``Cookie:
  edi-token=…`` (set by hand) or, while the auth service is down, ``?key=``.
  The client's cookie jar accepts nothing, so the ``edi-token`` cookie PASTA
  sets even on anonymous 403s is never stored or replayed to another caller.
* A 401 to a token re-exchanges the key once and retries.
* Every surfaced URL, endpoint label, cache key and error path is built
  without the ``key`` parameter; transport errors are raised ``from None`` so
  no traceback carries a keyed URL.
* Redirects are followed by hand (at most 3) and only to allow-listed hosts.
* 429 (honouring ``Retry-After``), 5xx and network failures are retried with
  backoff. PASTA publishes no rate limits, so one semaphore bounds
  concurrency.
* Bodies are read with a byte cap; responses are cached per family, PASTA
  responses per key identity.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

import httpx
import structlog

from edi_mcp import __version__
from edi_mcp.config import CacheConfig, EdiConfig
from edi_mcp.context import UpstreamStats
from edi_mcp.edi.auth import ApiKey, scrub_url
from edi_mcp.edi.cache import CacheFamily, CacheHit, CacheStats, TTLCache, cache_key
from edi_mcp.edi.tokens import TokenManager
from edi_mcp.errors import EdiApiError, ToolError, redact
from edi_mcp.logging import registered_secrets

log = structlog.get_logger("edi_mcp.http")

MAX_REDIRECTS = 3
_REDIRECTS = frozenset({301, 302, 303, 307, 308})
#: EDI user principals (``EDI-<40 hex>``) are removed from upstream error text.
_PRINCIPAL_RE = re.compile(r"EDI-[0-9a-f]{40}")
#: PASTA's 403 text names the caller: ``User 'EDI-<hex> (Display Name)' is not authorized``;
#: anchored on the fixed wording because names can contain apostrophes (O'Brien).
_USER_RE = re.compile(r"User '.*?' is not authorized")

CredentialKind = Literal["none", "token", "key"]


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def host_allowed(url: str, allowed: Sequence[str]) -> bool:
    """https only; exact host match, or ``*.example.org`` for any subdomain."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host:
        return False
    for pattern in allowed:
        pattern = pattern.lower().strip()
        if (pattern.startswith("*.") and host.endswith(pattern[1:])) or host == pattern:
            return True
    return False


def endpoint_label(method: str, url: str) -> str:
    """``GET host/path``: no query string, so never a credential."""
    parts = urlsplit(url)
    return f"{method} {(parts.hostname or '').lower()}{parts.path}"


@dataclass
class Fetched:
    """One upstream response body (possibly from cache)."""

    body: bytes
    status: int
    content_type: str | None
    url: str
    endpoint: str
    cache: CacheHit
    credential: CredentialKind

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")


@dataclass
class Streamed:
    """An open upstream response after redirects; iterate :meth:`chunks`, then let the
    context manager close it (closing early is fine: GMN ignores ``Range``)."""

    response: httpx.Response
    url: str
    endpoint: str
    content_type: str | None
    credential: CredentialKind

    def header(self, name: str) -> str | None:
        value = self.response.headers.get(name)
        return str(value) if value is not None else None

    def chunks(self) -> AsyncIterator[bytes]:
        return self.response.aiter_bytes()


@dataclass
class _Raw:
    body: bytes
    status: int
    content_type: str | None
    url: str
    credential: CredentialKind


class EdiClient:
    def __init__(
        self,
        config: EdiConfig,
        cache_config: CacheConfig,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.config = config
        self._clock = clock
        self._sleep = sleep
        self.cache = TTLCache(cache_config, clock=clock)
        self.pasta_host = host_of(config.pasta_base_url)
        self.allowed_hosts: tuple[str, ...] = tuple(
            sorted(
                {
                    host_of(u)
                    for u in (
                        config.pasta_base_url,
                        config.auth_base_url,
                        config.dataone_cn_url,
                        config.gmn_lter_url,
                        config.gmn_edi_url,
                        config.cite_url,
                    )
                }
            )
        )
        self._services = {
            self.pasta_host: "PASTA",
            host_of(config.auth_base_url): "The EDI auth service",
            host_of(config.dataone_cn_url): "DataONE",
            host_of(config.gmn_lter_url): "DataONE",
            host_of(config.gmn_edi_url): "DataONE",
            host_of(config.cite_url): "The EDI citation service",
        }
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        suffix = f" {config.user_agent_suffix}" if config.user_agent_suffix else ""
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=config.connect_timeout_s, read=config.read_timeout_s, write=10.0, pool=10.0
            ),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
            headers={
                "User-Agent": f"edi-mcp/{__version__} (+https://github.com/idss-mesa/edi-mcp){suffix}",
                "Accept-Encoding": "gzip",
            },
            # A jar that accepts no cookie: PASTA's Set-Cookie edi-token is never replayed.
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
            follow_redirects=False,
            transport=http_transport,
        )
        self.tokens = TokenManager(self._http, config, clock=wall_clock)

    # ------------------------------------------------------------------ helpers

    def is_pasta(self, url: str) -> bool:
        return host_of(url) == self.pasta_host

    def service(self, url: str) -> str:
        return self._services.get(host_of(url), host_of(url) or "upstream")

    async def _backoff(self, attempt: int) -> None:
        retries = self.config.retries
        delay = min(retries.backoff_base_s * (2 ** (attempt - 1)), retries.backoff_max_s)
        await self._sleep(delay + random.uniform(0, 0.25))  # noqa: S311 - jitter, not crypto

    def _retry_after(self, headers: Mapping[str, str]) -> float:
        value = headers.get("retry-after")
        if value is not None:
            try:
                return max(float(value), 0.0)
            except ValueError:
                pass
        return self.config.retries.retry_after_default_s

    def _error(
        self,
        status: int,
        detail: str,
        url: str,
        credential: CredentialKind,
        **kw: Any,
    ) -> EdiApiError:
        clean = _PRINCIPAL_RE.sub("EDI-…", redact(detail, registered_secrets()))
        clean = _USER_RE.sub("User '…' is not authorized", clean)
        return EdiApiError(
            status,
            clean[:300] or "no detail",
            urlsplit(url).path,
            credential_sent=credential != "none",
            service=self.service(url),
            **kw,
        )

    # ------------------------------------------------------------------ sending

    async def _send(
        self,
        url: str,
        params: Mapping[str, str],
        *,
        key: ApiKey | None,
        accept: str | None,
        stats: UpstreamStats,
        read_timeout_s: float | None = None,
    ) -> tuple[httpx.Response, CredentialKind]:
        """GET with retries and credential attachment; returns an open streamed response."""
        pasta = self.is_pasta(url)
        attempts = self.config.retries.max_attempts
        attempt = 0
        reexchanged = False
        while True:
            attempt += 1
            headers = {"Accept": accept} if accept else {}
            send_params = dict(params)
            credential: CredentialKind = "none"
            token: str | None = None
            if pasta and key is not None:
                cred = await self.tokens.credential(key)
                credential = cred.kind
                if cred.kind == "token":
                    token = cred.value
                    headers["Cookie"] = f"edi-token={cred.value}"
                else:
                    send_params["key"] = cred.value
            started = self._clock()
            try:
                async with self._semaphore:
                    request = self._http.build_request(
                        "GET", url, params=send_params or None, headers=headers
                    )
                    if read_timeout_s:
                        # Per request; ``timeout=None`` would disable timeouts altogether.
                        request.extensions["timeout"] = self._timeout(read_timeout_s).as_dict()
                    response = await self._http.send(request, stream=True)
            except httpx.HTTPError as exc:
                if attempt < attempts:
                    await self._backoff(attempt)
                    continue
                # ``from None``: the httpx exception's message can carry the keyed URL.
                raise self._error(
                    0, type(exc).__name__, url, credential, kind="transport"
                ) from None
            stats.requests += 1
            if credential != "none":
                stats.credential = credential
            log.debug(
                "edi.http",
                url=scrub_url(url),
                query_keys=sorted(params),
                status=response.status_code,
                ms=round((self._clock() - started) * 1000, 1),
                attempt=attempt,
                credential=credential,
            )
            status = response.status_code
            if status == 401 and token is not None and key is not None and not reexchanged:
                await response.aclose()
                self.tokens.invalidate(key, token)
                reexchanged = True
                attempt -= 1
                continue
            if status == 429 and attempt < attempts:
                await response.aclose()
                await self._sleep(self._retry_after(response.headers))
                continue
            if status >= 500 and attempt < attempts:
                await response.aclose()
                await self._backoff(attempt)
                continue
            return response, credential

    async def _read(self, response: httpx.Response, url: str, max_bytes: int) -> bytes:
        chunks: list[bytes] = []
        total = 0
        try:
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    raise ToolError(
                        "result_too_large",
                        f"{self.service(url)} returned more than {max_bytes} bytes.",
                        details={"maxBytes": max_bytes, "endpoint": endpoint_label("GET", url)},
                    )
                chunks.append(chunk)
        finally:
            await response.aclose()
        return b"".join(chunks)

    def _timeout(self, read_timeout_s: float) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.config.connect_timeout_s, read=read_timeout_s, write=10.0, pool=10.0
        )

    async def _open(
        self,
        url: str,
        params: Mapping[str, str],
        *,
        key: ApiKey | None,
        accept: str | None,
        stats: UpstreamStats,
        allowed_hosts: Sequence[str] | None = None,
        read_timeout_s: float | None = None,
    ) -> tuple[httpx.Response, str, CredentialKind]:
        """Follow allow-listed redirects to a 2xx response and return it open.

        Every hop is checked against ``allowed_hosts`` (default: the EDI/DataONE hosts);
        an HTTP error status is read (capped) and raised as :class:`EdiApiError`.
        """
        hosts = self.allowed_hosts if allowed_hosts is None else tuple(allowed_hosts)
        current, current_params = url, dict(params)
        for _hop in range(MAX_REDIRECTS + 1):
            if not host_allowed(current, hosts):
                raise ToolError(
                    "upstream_error",
                    "An upstream redirect pointed outside the EDI/DataONE host allow-list.",
                    details={"host": host_of(current), "allowedHosts": list(hosts)},
                )
            response, credential = await self._send(
                current,
                current_params,
                key=key,
                accept=accept,
                stats=stats,
                read_timeout_s=read_timeout_s,
            )
            if response.status_code in _REDIRECTS:
                location = response.headers.get("location")
                await response.aclose()
                if not location:
                    raise self._error(
                        response.status_code, "redirect without Location", current, credential
                    )
                current, current_params = urljoin(current, location), {}
                continue
            if response.status_code >= 400:
                body = await self._read(response, current, 64 * 1024)
                raise self._error(
                    response.status_code,
                    body.decode("utf-8", "replace").strip(),
                    current,
                    credential,
                    content_type=_content_type(response),
                    retry_after_s=self._retry_after(response.headers)
                    if response.status_code == 429
                    else None,
                )
            return response, current, credential
        raise ToolError(
            "upstream_error", "Too many upstream redirects.", details={"url": scrub_url(url)}
        )

    async def _request(
        self,
        url: str,
        params: Mapping[str, str],
        *,
        key: ApiKey | None,
        accept: str | None,
        stats: UpstreamStats,
        max_bytes: int,
    ) -> _Raw:
        response, current, credential = await self._open(
            url, params, key=key, accept=accept, stats=stats
        )
        body = await self._read(response, current, max_bytes)
        return _Raw(
            body, response.status_code, _content_type(response), scrub_url(current), credential
        )

    # ------------------------------------------------------------------ public

    async def get(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        key: ApiKey | None = None,
        accept: str | None = None,
        cache: CacheFamily | None = None,
        ttl_s: float | None = None,
        stats: UpstreamStats | None = None,
        max_bytes: int | None = None,
    ) -> Fetched:
        """GET ``url``; raises :class:`EdiApiError` for HTTP >= 400 (after retries).

        ``key`` is attached only when ``url`` is on the PASTA host; elsewhere it
        is ignored, so callers may pass it unconditionally.
        """
        stats = stats if stats is not None else UpstreamStats()
        clean = {k: str(v) for k, v in (params or {}).items() if v is not None}
        if any(k.lower() == "key" for k in clean):
            raise ValueError("credential parameters are attached by the client, never by callers")
        endpoint = endpoint_label("GET", url)
        stats.record_endpoint(endpoint)
        pasta_key = key if key is not None and self.is_pasta(url) else None
        scope = pasta_key.identity() if pasta_key is not None else None
        cap = max_bytes or self.config.max_response_bytes

        async def fetch() -> _Raw:
            return await self._request(
                url, clean, key=pasta_key, accept=accept, stats=stats, max_bytes=cap
            )

        hit: CacheHit = "bypass"
        if cache is None:
            raw = await fetch()
        else:
            raw, hit = await self.cache.get_or_fetch(
                cache,
                cache_key("GET", url, {**clean, "@accept": accept}, scope=scope),
                fetch,
                ttl_s=ttl_s,
            )
            if hit in ("hit", "stale"):
                stats.cache_hits += 1
        return Fetched(
            body=raw.body,
            status=raw.status,
            content_type=raw.content_type,
            url=raw.url,
            endpoint=endpoint,
            cache=hit,
            credential=raw.credential,
        )

    @asynccontextmanager
    async def stream(
        self,
        url: str,
        params: Mapping[str, Any] | None = None,
        *,
        key: ApiKey | None = None,
        accept: str | None = None,
        stats: UpstreamStats | None = None,
        allowed_hosts: Sequence[str] | None = None,
        read_timeout_s: float | None = None,
    ) -> AsyncIterator[Streamed]:
        """Open ``url`` for streaming (never cached); same credential, retry, redirect and
        error rules as :meth:`get`. ``allowed_hosts`` narrows the redirect allow-list."""
        stats = stats if stats is not None else UpstreamStats()
        clean = {k: str(v) for k, v in (params or {}).items() if v is not None}
        if any(k.lower() == "key" for k in clean):
            raise ValueError("credential parameters are attached by the client, never by callers")
        endpoint = endpoint_label("GET", url)
        stats.record_endpoint(endpoint)
        pasta_key = key if key is not None and self.is_pasta(url) else None
        response, current, credential = await self._open(
            url,
            clean,
            key=pasta_key,
            accept=accept,
            stats=stats,
            allowed_hosts=allowed_hosts,
            read_timeout_s=read_timeout_s,
        )
        try:
            yield Streamed(
                response=response,
                url=scrub_url(current),
                endpoint=endpoint,
                content_type=_content_type(response),
                credential=credential,
            )
        except httpx.HTTPError as exc:
            raise self._error(
                0, type(exc).__name__, current, credential, kind="transport"
            ) from None
        finally:
            await response.aclose()

    def cache_stats(self) -> CacheStats:
        return self.cache.stats()

    async def aclose(self) -> None:
        await self._http.aclose()


def _content_type(response: httpx.Response) -> str | None:
    return (response.headers.get("content-type") or "").split(";")[0] or None


__all__ = ["EdiClient", "Fetched", "Streamed", "endpoint_label", "host_allowed"]
