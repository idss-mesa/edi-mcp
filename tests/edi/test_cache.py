"""TTL cache: single flight, stale-if-error, LRU caps."""

from __future__ import annotations

import asyncio

import pytest

from edi_mcp.config import CacheConfig
from edi_mcp.edi.cache import FAMILY_CAPS, TTLCache


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_single_flight_and_hits() -> None:
    cache = TTLCache(CacheConfig(), clock=Clock())
    calls = 0

    async def fetch() -> int:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return 7

    results = await asyncio.gather(*(cache.get_or_fetch("search", "k", fetch) for _ in range(4)))
    assert [v for v, _ in results] == [7] * 4 and calls == 1
    assert sorted(h for _, h in results).count("miss") == 1
    assert cache.stats().hits == 3 and cache.stats().families == {"search": 1}


async def test_stale_if_error_then_raise() -> None:
    clock = Clock()
    cache = TTLCache(CacheConfig.model_validate({"stale_if_error_s": 100}), clock=clock)

    async def ok() -> str:
        return "v1"

    async def boom() -> str:
        raise RuntimeError("down")

    await cache.get_or_fetch("feeds", "k", ok)
    clock.now += cache.ttl_for("feeds") + 10
    assert await cache.get_or_fetch("feeds", "k", boom) == ("v1", "stale")
    clock.now += 1000
    with pytest.raises(RuntimeError):
        await cache.get_or_fetch("feeds", "k", boom)


async def test_disabled_and_zero_ttl_bypass() -> None:
    cache = TTLCache(CacheConfig.model_validate({"enabled": False}))

    async def fetch() -> int:
        return 1

    assert await cache.get_or_fetch("search", "k", fetch) == (1, "bypass")
    live = TTLCache(CacheConfig())
    assert await live.get_or_fetch("search", "k", fetch, ttl_s=0) == (1, "bypass")


def test_caps_and_invalidate() -> None:
    cache = TTLCache(CacheConfig.model_validate({"max_entries": 3}))
    for i in range(FAMILY_CAPS["feeds"] + 2):
        cache.put("feeds", f"k{i}", i, ttl_s=60)
    assert cache.stats().entries == 3
    assert cache.invalidate("feeds") == 3 and cache.invalidate() == 0
