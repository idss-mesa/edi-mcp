"""In-memory TTL cache with single-flight and stale-if-error.

Entries live in per-family LRU maps (families match ``cache.ttl_s``).
Concurrent misses on one key perform a single fetch. An expired entry is
served (reported as ``stale``) for up to ``cache.stale_if_error_s`` when its
refresh fails.

Cache keys never contain the API key or an ``edi-token``: PASTA keys carry
only the key's non-reversible ``identity()`` (ported from neon-mcp, without
refresh-ahead).
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar
from urllib.parse import urlencode

import structlog

from edi_mcp.config import CacheConfig

T = TypeVar("T")

CacheFamily = Literal["listings", "search", "metadata", "reports", "feeds", "citations"]
CacheHit = Literal["hit", "miss", "stale", "bypass"]

FAMILY_CAPS: dict[str, int] = {
    "listings": 128,
    "search": 128,
    "metadata": 64,
    "reports": 64,
    "feeds": 32,
    "citations": 256,
}

log = structlog.get_logger("edi_mcp.cache")


@dataclass
class _Entry:
    value: Any
    expires_at: float


@dataclass
class CacheStats:
    entries: int
    hits: int
    misses: int
    stale_served: int
    families: dict[str, int] = field(default_factory=dict)


def cache_key(
    method: str,
    url: str,
    params: Mapping[str, Any] | None = None,
    *,
    scope: str | None = None,
) -> str:
    """Canonical key: method, URL without query, sorted params, credential identity."""
    items = sorted((k, str(v)) for k, v in (params or {}).items() if v is not None)
    key = f"{method.upper()} {url}?{urlencode(items)}"
    if scope:
        key += "|" + scope
    return key


class TTLCache:
    def __init__(self, cfg: CacheConfig, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._cfg = cfg
        self._clock = clock
        self._data: dict[str, OrderedDict[str, _Entry]] = {f: OrderedDict() for f in FAMILY_CAPS}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self.hits = 0
        self.misses = 0
        self.stale_served = 0

    def ttl_for(self, family: CacheFamily) -> float:
        return float(getattr(self._cfg.ttl_s, family))

    async def get_or_fetch(
        self,
        family: CacheFamily,
        key: str,
        fetch: Callable[[], Awaitable[T]],
        *,
        ttl_s: float | None = None,
    ) -> tuple[T, CacheHit]:
        ttl = self.ttl_for(family) if ttl_s is None else float(ttl_s)
        if not self._cfg.enabled or ttl <= 0:
            return await fetch(), "bypass"

        entry = self._data[family].get(key)
        if entry is not None and self._clock() < entry.expires_at:
            self.hits += 1
            self._data[family].move_to_end(key)
            return entry.value, "hit"

        lock = self._locks.setdefault((family, key), asyncio.Lock())
        try:
            async with lock:
                entry = self._data[family].get(key)
                now = self._clock()
                if entry is not None and now < entry.expires_at:
                    self.hits += 1
                    return entry.value, "hit"
                self.misses += 1
                try:
                    value = await fetch()
                except Exception:
                    if entry is not None and now - entry.expires_at <= self._cfg.stale_if_error_s:
                        self.stale_served += 1
                        log.warning(
                            "cache.stale_served",
                            family=family,
                            age_s=round(now - entry.expires_at, 1),
                        )
                        return entry.value, "stale"
                    raise
                self.put(family, key, value, ttl_s=ttl)
                return value, "miss"
        finally:
            if not lock.locked():
                self._locks.pop((family, key), None)

    def put(self, family: CacheFamily, key: str, value: Any, *, ttl_s: float) -> None:
        if not self._cfg.enabled or ttl_s <= 0:
            return
        bucket = self._data[family]
        bucket[key] = _Entry(value=value, expires_at=self._clock() + ttl_s)
        bucket.move_to_end(key)
        while len(bucket) > FAMILY_CAPS[family]:
            bucket.popitem(last=False)
        while sum(len(b) for b in self._data.values()) > self._cfg.max_entries:
            max(self._data.values(), key=len).popitem(last=False)

    def invalidate(self, family: CacheFamily | None = None) -> int:
        removed = 0
        for fam in [family] if family else list(self._data):
            removed += len(self._data[fam])
            self._data[fam].clear()
        return removed

    def stats(self) -> CacheStats:
        families = {name: len(bucket) for name, bucket in self._data.items() if bucket}
        return CacheStats(
            entries=sum(families.values()),
            hits=self.hits,
            misses=self.misses,
            stale_served=self.stale_served,
            families=families,
        )
