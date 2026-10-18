"""EdiClient + TokenManager: credential rules (DESIGN.md D4) and transport behaviour."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from structlog.testing import capture_logs

from edi_mcp.config import Config
from edi_mcp.context import UpstreamStats
from edi_mcp.edi.auth import ApiKey, jwt_expiry, scrub_url
from edi_mcp.edi.cache import cache_key
from edi_mcp.edi.client import EdiClient, endpoint_label, host_allowed
from edi_mcp.errors import EdiApiError, ToolError, map_api_error
from edi_mcp.logging import register_secret
from tests.fixture_router import FixtureRouter, Reply, fake_jwt
from tests.helpers import TEST_KEY

PASTA = "https://pasta.lternet.edu/package"
SCOPES = f"{PASTA}/eml"
REVISIONS = f"{PASTA}/eml/knb-lter-hbr/14"
SOLR = "https://cn.dataone.org/cn/v2/query/solr/"
SOLR_PING = {
    "q": "*:*",
    "fq": 'formatType:METADATA AND datasource:("urn:node:EDI" OR "urn:node:LTER")',
    "rows": "0",
    "wt": "json",
}
GMN_EML = (
    "https://gmn.lternet.edu/mn/v2/object/"
    "https%3A%2F%2Fpasta.lternet.edu%2Fpackage%2Fmetadata%2Feml%2Fknb-lter-hbr%2F14%2F22"
)


async def _no_sleep(_: float) -> None:
    return None


@pytest.fixture
async def make_client(router: FixtureRouter) -> AsyncIterator[Callable[..., EdiClient]]:
    clients: list[EdiClient] = []

    def _make(**edi: object) -> EdiClient:
        cfg = Config.model_validate({"edi": edi})
        client = EdiClient(cfg.edi, cfg.cache, http_transport=router.transport, sleep=_no_sleep)
        clients.append(client)
        return client

    yield _make
    for client in clients:
        await client.aclose()


@pytest.fixture
def key() -> ApiKey:
    return ApiKey(TEST_KEY, "config")


async def test_token_goes_to_pasta_only(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    client = make_client()
    stats = UpstreamStats()
    fetched = await client.get(SCOPES, key=key, stats=stats)
    assert fetched.credential == "token" and stats.credential == "token"
    assert "knb-lter-hbr" in fetched.text.splitlines()
    pasta_call = router.calls[-1]
    assert pasta_call.cookie and pasta_call.cookie.startswith("edi-token=")
    assert "key" not in pasta_call.params
    # The key passed along to DataONE is ignored: the router fails on any credential there.
    other = await client.get(SOLR, SOLR_PING, key=key, stats=stats)
    assert other.credential == "none"
    assert router.calls[-1].cookie is None
    assert len(router.auth_calls("/key")) == 1
    assert stats.endpoints == [
        "GET pasta.lternet.edu/package/eml",
        "GET cn.dataone.org/cn/v2/query/solr/",
    ]


async def test_pasta_set_cookie_is_never_replayed(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    """PASTA sets edi-token (Domain=.lternet.edu) even on 403s; it must not stick."""
    client = make_client()
    with pytest.raises(EdiApiError) as exc:
        await client.get(SCOPES)
    assert exc.value.status == 403 and not exc.value.credential_sent
    await client.get(GMN_EML)  # gmn.lternet.edu would match the cookie's domain
    assert router.calls[-1].cookie is None
    with pytest.raises(EdiApiError):
        await client.get(SCOPES)
    assert router.calls[-1].cookie is None
    await client.get(SCOPES, key=key)
    assert router.calls[-1].cookie != f"edi-token={fake_jwt(0, 0)}"


async def test_concurrent_calls_exchange_once(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    client = make_client()
    await asyncio.gather(*(client.get(SCOPES, key=key) for _ in range(5)))
    assert len(router.auth_calls("/key")) == 1
    assert client.tokens.exchanges(key) == 1


async def test_token_refreshed_when_close_to_expiry(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    router.token_lifetime_s = 1800  # under the 1 h refresh margin
    client = make_client()
    await client.get(SCOPES, key=key)
    await client.get(REVISIONS, key=key)
    assert len(router.auth_calls("/key")) == 1
    assert len(router.auth_calls("/token/refresh")) == 1


async def test_failed_refresh_falls_back_to_exchange(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    router.token_lifetime_s = 1800
    client = make_client()
    await client.get(SCOPES, key=key)
    router.revoke_tokens()  # refresh now answers 401
    fetched = await client.get(REVISIONS, key=key)
    assert fetched.credential == "token"
    assert len(router.auth_calls("/key")) == 2


async def test_401_reexchanges_once_and_retries(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    client = make_client()
    await client.get(SCOPES, key=key)
    router.revoke_tokens()  # PASTA now rejects the cached token
    fetched = await client.get(REVISIONS, key=key)
    assert fetched.status == 200
    assert len(router.auth_calls("/key")) == 2


async def test_persistent_401_is_upstream_forbidden(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    client = make_client()
    router.add(
        "GET pasta.lternet.edu/package/eml",
        Reply(401, b"EDI token validation failed", "text/plain"),
    )
    with pytest.raises(EdiApiError) as exc:
        await client.get(SCOPES, key=key)
    assert map_api_error(exc.value).code == "upstream_forbidden"
    assert len(router.auth_calls("/key")) == 2  # one re-exchange, then give up


async def test_rejected_key_is_upstream_forbidden_without_fallback(
    make_client: Callable[..., EdiClient], router: FixtureRouter
) -> None:
    client = make_client()
    with pytest.raises(EdiApiError) as exc:
        await client.get(SCOPES, key=ApiKey("not-the-right-key", "config"))
    err = map_api_error(exc.value)
    assert err.code == "upstream_forbidden"
    assert "EDI auth service" in err.message
    assert {c.host for c in router.calls} == {"auth.edirepository.org"}


async def test_auth_outage_falls_back_to_key_param_without_leaking(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    router.auth_mode = "down"
    client = make_client()
    stats = UpstreamStats()
    with capture_logs() as logs:
        fetched = await client.get(SCOPES, key=key, stats=stats, cache="listings")
        again = await client.get(REVISIONS, key=key, stats=stats)
    assert fetched.credential == again.credential == "key" == stats.credential
    assert router.calls[-1].params["key"] == TEST_KEY
    assert len(router.auth_calls("/key")) == 1  # the outage is remembered
    surfaced = json.dumps(
        [fetched.url, fetched.endpoint, again.url, stats.endpoints, logs], default=str
    )
    assert TEST_KEY not in surfaced
    assert any(e["event"] == "auth.fallback_to_key_param" for e in logs)
    assert all(TEST_KEY not in k for k in client.cache._data["listings"])


async def test_auth_5xx_also_falls_back(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    router.auth_mode = "error"
    fetched = await make_client().get(SCOPES, key=key)
    assert fetched.credential == "key"


async def test_transport_failure_with_key_param_leaks_nothing(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    register_secret(TEST_KEY)
    router.auth_mode = "down"
    router.inject(httpx.ConnectError, times=3)
    client = make_client()
    with capture_logs() as logs, pytest.raises(EdiApiError) as exc:
        await client.get(SCOPES, key=key)
    error = exc.value
    assert error.kind == "transport" and error.credential_sent
    assert error.__cause__ is None and error.__suppress_context__
    payload = map_api_error(error).to_payload()
    assert payload["error"]["code"] == "upstream_unavailable"
    text = json.dumps([str(error), error.path, payload, logs], default=str)
    assert TEST_KEY not in text
    assert len([c for c in router.calls if c.host == "pasta.lternet.edu"]) == 3


async def test_5xx_retried_then_succeeds(
    make_client: Callable[..., EdiClient], router: FixtureRouter
) -> None:
    router.inject(Reply(502, b"<html>bad gateway</html>", "text/html"), times=2)
    stats = UpstreamStats()
    fetched = await make_client().get(GMN_EML, stats=stats)
    assert fetched.status == 200 and stats.requests == 3


async def test_429_exhausted_is_rate_limited(
    make_client: Callable[..., EdiClient], router: FixtureRouter
) -> None:
    router.inject(Reply(429, b"slow down", "text/plain", {"retry-after": "2"}), times=3)
    with pytest.raises(EdiApiError) as exc:
        await make_client().get(GMN_EML)
    err = map_api_error(exc.value)
    assert err.code == "rate_limited" and err.details["retryAfterSeconds"] == 2.0
    assert exc.value.service == "DataONE"


async def test_redirects_followed_only_within_allow_list(
    make_client: Callable[..., EdiClient], router: FixtureRouter
) -> None:
    client = make_client()
    router.add(
        "GET cn.dataone.org/cn/v2/resolve/x",
        Reply(303, b"", "text/plain", {"location": GMN_EML}),
    )
    fetched = await client.get("https://cn.dataone.org/cn/v2/resolve/x")
    assert fetched.url == "https://gmn.lternet.edu/mn/v2/object/" + GMN_EML.rsplit("/", 1)[1]
    router.add(
        "GET cn.dataone.org/cn/v2/resolve/y",
        Reply(302, b"", "text/plain", {"location": "https://evil.example.org/steal"}),
    )
    with pytest.raises(ToolError) as exc:
        await client.get("https://cn.dataone.org/cn/v2/resolve/y")
    assert exc.value.code == "upstream_error"
    assert exc.value.details["host"] == "evil.example.org"


async def test_redirect_without_location_is_an_error(
    make_client: Callable[..., EdiClient], router: FixtureRouter
) -> None:
    router.add("GET cn.dataone.org/cn/v2/resolve/z", Reply(302, b"", "text/plain"))
    with pytest.raises(EdiApiError) as exc:
        await make_client().get("https://cn.dataone.org/cn/v2/resolve/z")
    assert exc.value.status == 302


async def test_redirect_loop_is_cut(
    make_client: Callable[..., EdiClient], router: FixtureRouter
) -> None:
    loop = "https://cn.dataone.org/cn/v2/resolve/loop"
    router.add(
        "GET cn.dataone.org/cn/v2/resolve/loop", Reply(302, b"", "text/plain", {"location": loop})
    )
    with pytest.raises(ToolError, match="Too many"):
        await make_client().get(loop)


async def test_body_cap(make_client: Callable[..., EdiClient]) -> None:
    with pytest.raises(ToolError) as exc:
        await make_client().get(GMN_EML, max_bytes=1024)
    assert exc.value.code == "result_too_large" and exc.value.details["maxBytes"] == 1024


async def test_cache_hits_skip_the_network(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    client = make_client()
    stats = UpstreamStats()
    first = await client.get(SCOPES, key=key, cache="listings", stats=stats)
    second = await client.get(SCOPES, key=key, cache="listings", stats=stats)
    assert (first.cache, second.cache) == ("miss", "hit")
    assert stats.requests == 1 and stats.cache_hits == 1
    assert client.cache_stats().entries == 1


async def test_upstream_error_text_drops_principals(
    make_client: Callable[..., EdiClient], router: FixtureRouter, key: ApiKey
) -> None:
    principal = "EDI-" + "a" * 40
    router.add(
        "GET pasta.lternet.edu/package/eml/knb-lter-hbr/14",
        Reply(
            403,
            f"User '{principal} (Ada Lovelace)' is not authorized to read 'x'".encode(),
            "text/plain",
        ),
    )
    with pytest.raises(EdiApiError) as exc:
        await make_client().get(REVISIONS, key=key)
    assert principal not in exc.value.detail and "Lovelace" not in exc.value.detail
    assert exc.value.detail.startswith("User '…' is not authorized")


async def test_callers_cannot_send_credential_params(make_client: Callable[..., EdiClient]) -> None:
    with pytest.raises(ValueError, match="credential"):
        await make_client().get(SCOPES, {"key": "x"})


def test_cache_key_scope_separates_identities() -> None:
    a = cache_key("GET", SCOPES, {"b": 1, "a": None}, scope="key:aaa")
    b = cache_key("GET", SCOPES, {"b": 1}, scope="key:bbb")
    assert a != b and a.startswith("GET https://pasta.lternet.edu/package/eml?b=1")


def test_scrub_url_and_helpers() -> None:
    register_secret("s3cr3t-value")
    assert scrub_url(f"{SCOPES}?key=abc&q=1") == f"{SCOPES}?q=1"
    assert scrub_url(f"{SCOPES}?KEY=abc") == SCOPES
    assert "s3cr3t-value" not in scrub_url("https://x.org/a/s3cr3t-value")
    assert endpoint_label("GET", f"{SCOPES}?key=abc") == "GET pasta.lternet.edu/package/eml"
    assert host_allowed("https://gmn.lternet.edu/x", ["*.lternet.edu"])
    assert not host_allowed("http://pasta.lternet.edu/x", ["pasta.lternet.edu"])
    assert not host_allowed("https://evil.org/x", ["pasta.lternet.edu"])


def test_jwt_expiry() -> None:
    assert jwt_expiry(fake_jwt(1234.0, 1)) == 1234.0
    assert jwt_expiry("not-a-jwt") is None
    assert jwt_expiry("a.!!!.c") is None


@pytest.mark.parametrize("level", ["info", "debug"])
async def test_key_param_never_reaches_stderr_logs(
    level: str,
    make_client: Callable[..., EdiClient],
    router: FixtureRouter,
    key: ApiKey,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """httpx logs full request URLs via stdlib logging; the ?key= fallback must not show."""
    from edi_mcp.logging import setup_logging

    setup_logging(level, "stdio")
    try:
        router.auth_mode = "down"
        client = make_client()
        fetched = await client.get(SCOPES, key=key)
        assert fetched.credential == "key"
        router.inject(httpx.ConnectError, times=3)
        with pytest.raises(EdiApiError):
            await client.get(REVISIONS, key=key)
        captured = capsys.readouterr()
        assert "edi.http" in captured.err or level == "info"
        assert TEST_KEY not in captured.err + captured.out
    finally:
        setup_logging("warning", "stdio")
