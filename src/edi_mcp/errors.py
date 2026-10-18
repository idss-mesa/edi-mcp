"""Structured error types for edi-mcp.

Tool handlers raise :class:`ToolError` for every user-facing failure; the
server boundary turns it into an ``isError`` tool result whose
``structuredContent`` is ``{"error": {"code", "message", "details", "hint"}}``.
Python tracebacks never reach the wire.

:class:`EdiApiError` is what the HTTP client raises for a failed upstream
call; :func:`map_api_error` translates it into a :class:`ToolError`. Since
2026-07-30 PASTA answers every anonymous request with 403 (401 for the audit
service), so 401/403 without credentials is ``auth_required``. With credentials, 401
is ``upstream_forbidden`` for a bad or expired key (DESIGN.md D2: never
silently downgraded to DataONE) and 403 is ``upstream_forbidden`` with
``reason: access_restricted`` (the key works but the package is restricted).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

ErrorCode = Literal[
    "invalid_argument",
    "not_found",
    "ambiguous_input",
    "auth_required",
    "upstream_forbidden",
    "rate_limited",
    "upstream_error",
    "upstream_unavailable",
    "feature_unavailable",
    "not_available_in_http_mode",
    "download_limit_exceeded",
    "download_denied",
    "checksum_mismatch",
    "result_too_large",
    "unknown_tool",
    "internal_error",
]

#: Resource every ``auth_required`` error points at.
API_KEY_GUIDE = "edi://guide/api-key"
#: Where EDI users create an API access key.
KEY_PAGE_URL = "https://auth.edirepository.org/auth/ui/key"

AUTH_REQUIRED_MESSAGE = (
    "This needs an EDI API key: since 2026-07-30 every PASTA request must be authenticated. "
    f"Sign in at {KEY_PAGE_URL}, create a key with your own profile as Principal, and set "
    "EDI_API_KEY in the server's environment; in HTTP mode send the X-EDI-Key header. "
    "Search, metadata, entity download and citation still work without a key (via DataONE)."
)


class ToolError(Exception):
    """A structured, user-facing failure raised from a tool handler.

    ``code`` is a stable machine-readable :data:`ErrorCode`; ``message`` is
    safe to show a user and never contains a key or token; ``details`` is
    JSON-serializable context; ``hint`` is an optional one-line remedy.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code: ErrorCode = code
        self.message = message
        self.details: dict[str, Any] = dict(details) if details else {}
        self.hint = hint

    def to_payload(self) -> dict[str, Any]:
        """Return the ``{"error": {...}}`` structure sent as ``structuredContent``."""
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
        if self.hint:
            error["hint"] = self.hint
        return {"error": error}

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"ToolError(code={self.code!r}, message={self.message!r})"


class InputRequired(Exception):
    """Raised by a handler that needs one more round trip with the user (MRTR).

    The server boundary turns it into an ``InputRequiredResult`` carrying an
    ``elicitation/create`` form. ``state`` travels out to the client and back
    as ``requestState``; it must hold only the question being asked — never a
    key, a token, a filesystem path or an authorization decision — because the
    client controls it by the time it returns.
    """

    def __init__(
        self,
        *,
        key: str,
        message: str,
        requested_schema: Mapping[str, Any],
        state: Mapping[str, Any],
    ) -> None:
        super().__init__(message)
        self.key = key
        self.message = message
        self.requested_schema: dict[str, Any] = dict(requested_schema)
        self.state: dict[str, Any] = dict(state)


class EdiApiError(Exception):
    """A failed upstream call (PASTA, IAM, DataONE or the citation service).

    ``kind`` distinguishes an HTTP error status (``http``), a network failure
    or timeout after retries (``transport``, ``status == 0``) and a response
    that could not be parsed (``decode``). ``path`` is already scrubbed of
    credentials by the client.
    """

    def __init__(
        self,
        status: int,
        detail: str,
        path: str,
        *,
        retry_after_s: float | None = None,
        headers: Mapping[str, str] | None = None,
        kind: Literal["http", "transport", "decode"] = "http",
        content_type: str | None = None,
        credential_sent: bool = False,
        service: str = "PASTA",
    ) -> None:
        super().__init__(f"{status} {path}: {detail}")
        self.status = status
        self.detail = detail
        self.path = path
        self.retry_after_s = retry_after_s
        self.headers: dict[str, str] = dict(headers or {})
        self.kind = kind
        self.content_type = content_type
        #: Whether the failed request carried an EDI credential (cookie or key).
        self.credential_sent = credential_sent
        #: Human name of the upstream service, used in messages.
        self.service = service


def redact(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of each non-empty secret in ``text`` with ``***``."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def auth_required_error(*, tool: str | None = None, endpoint: str | None = None) -> ToolError:
    """The ``auth_required`` error for a PASTA-only operation without a key."""
    details: dict[str, Any] = {"guide": API_KEY_GUIDE, "keySource": "none"}
    if tool:
        details["tool"] = tool
    if endpoint:
        details["endpoint"] = endpoint
    return ToolError(
        "auth_required",
        AUTH_REQUIRED_MESSAGE,
        details=details,
        hint="Read edi://guide/api-key.",
    )


def map_api_error(
    exc: EdiApiError,
    *,
    credential_sent: bool | None = None,
    entity: str | None = None,
    identifier: str | None = None,
    secrets: Iterable[str] = (),
) -> ToolError:
    """Translate an upstream failure into a :class:`ToolError`."""
    secrets = tuple(secrets)
    if credential_sent is None:
        credential_sent = exc.credential_sent
    detail = redact(exc.detail or "", secrets)[:500]
    endpoint = redact(exc.path, secrets)
    service = exc.service

    if exc.kind == "transport":
        return ToolError(
            "upstream_unavailable",
            f"{service} could not be reached (network error or timeout).",
            details={"reason": detail, "endpoint": endpoint},
            hint="Retry in a moment; call edi_ping to check the configuration.",
        )
    if exc.kind == "decode":
        return ToolError(
            "upstream_error",
            f"{service} returned a response that could not be parsed.",
            details={"status": exc.status, "contentType": exc.content_type, "endpoint": endpoint},
        )

    status = exc.status
    if status in (401, 403):
        if not credential_sent:
            return auth_required_error(endpoint=endpoint)
        if status == 403:
            # A bad key or token gets 401; 403 with credentials means the key's user is
            # authenticated but not on the resource's access list (RESEARCH.md section 5).
            what = f"{entity} {identifier!r}" if entity and identifier else "this resource"
            return ToolError(
                "upstream_forbidden",
                f"{service} accepted the EDI credentials but does not let this key's user read "
                f"{what} (HTTP 403): it is restricted to named users or groups.",
                details={
                    "reason": "access_restricted",
                    "endpoint": endpoint,
                    "status": status,
                    "upstream": detail,
                },
                hint="Ask the package contact for access, or choose another package.",
            )
        return ToolError(
            "upstream_forbidden",
            f"{service} rejected the EDI credentials (HTTP {status}). The API key is usually "
            "mistyped, expired or deleted, or assigned to a group without access. Check the "
            f"EDI_API_KEY value (or the X-EDI-Key header) or create a new key at {KEY_PAGE_URL}.",
            details={
                "guide": API_KEY_GUIDE,
                "endpoint": endpoint,
                "status": status,
                "upstream": detail,
            },
            hint="Read edi://guide/api-key.",
        )
    if status in (404, 410):
        details: dict[str, Any] = {"endpoint": endpoint}
        if entity:
            details["entity"] = entity
        if identifier:
            details["identifier"] = identifier
        what = f"{entity} {identifier!r}" if entity and identifier else "The requested item"
        return ToolError(
            "not_found", f"{what} was not found. {service} said: {detail}", details=details
        )
    if status == 400:
        return ToolError(
            "invalid_argument",
            f"{service} rejected the request: {detail}",
            details={"endpoint": endpoint},
        )
    if status == 429:
        return ToolError(
            "rate_limited",
            f"{service} rate limit was exceeded; wait before retrying.",
            details={"retryAfterSeconds": exc.retry_after_s, "endpoint": endpoint},
        )
    if status >= 500:
        return ToolError(
            "upstream_error",
            f"{service} failed with HTTP {status}.",
            details={"status": status, "endpoint": endpoint, "body": detail[:200]},
        )
    return ToolError(
        "upstream_error",
        f"{service} answered HTTP {status}: {detail}",
        details={"status": status, "endpoint": endpoint},
    )
