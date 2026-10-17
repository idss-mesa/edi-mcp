from __future__ import annotations

from typing import Any

import pytest

from edi_mcp.errors import (
    EdiApiError,
    InputRequired,
    ToolError,
    auth_required_error,
    map_api_error,
    redact,
)


def err(status: int, detail: str = "x", **kw: Any) -> EdiApiError:
    return EdiApiError(status, detail, "/package/eml/knb-lter-hbr/14", **kw)


@pytest.mark.parametrize("status", [401, 403])
def test_401_403_without_credentials_is_auth_required(status: int) -> None:
    e = map_api_error(err(status, "User 'EDI-… (Public Access)' is not authorized"))
    assert e.code == "auth_required"
    assert e.details == {
        "guide": "edi://guide/api-key",
        "keySource": "none",
        "endpoint": "/package/eml/knb-lter-hbr/14",
    }
    assert "auth.edirepository.org/auth/ui/key" in e.message and "EDI_API_KEY" in e.message


@pytest.mark.parametrize("status", [401, 403])
def test_401_403_with_credentials_is_upstream_forbidden(status: int) -> None:
    e = map_api_error(err(status, "EDI token validation failed", credential_sent=True))
    assert e.code == "upstream_forbidden"
    assert e.details["status"] == status and e.details["guide"] == "edi://guide/api-key"
    assert map_api_error(err(status), credential_sent=True).code == "upstream_forbidden"
    assert map_api_error(err(status, credential_sent=True), credential_sent=False).code == (
        "auth_required"
    )


def test_not_found_names_the_entity() -> None:
    e = map_api_error(err(404, "Document not found"), entity="package", identifier="edi.999.1")
    assert e.code == "not_found"
    assert e.details["identifier"] == "edi.999.1"
    assert "package 'edi.999.1'" in e.message


@pytest.mark.parametrize(
    ("status", "detail", "code"),
    [
        (400, "Bad Request", "invalid_argument"),
        (404, "not found", "not_found"),
        (410, "gone", "not_found"),
        (429, "slow down", "rate_limited"),
        (500, "boom", "upstream_error"),
        (502, "<html>", "upstream_error"),
        (418, "teapot", "upstream_error"),
    ],
)
def test_status_table(status: int, detail: str, code: str) -> None:
    assert map_api_error(err(status, detail)).code == code


def test_service_name_and_rate_limit_details() -> None:
    e = map_api_error(err(429, retry_after_s=2.0, service="DataONE"))
    assert e.details["retryAfterSeconds"] == 2.0
    assert e.message.startswith("DataONE")


def test_transport_and_decode_kinds() -> None:
    assert (
        map_api_error(EdiApiError(0, "ConnectError", "/package/eml", kind="transport")).code
        == "upstream_unavailable"
    )
    decoded = map_api_error(
        EdiApiError(200, "not xml", "/package/search/eml", kind="decode", content_type="text/html")
    )
    assert decoded.code == "upstream_error"
    assert decoded.details["contentType"] == "text/html"


def test_secrets_are_redacted_from_messages_and_endpoints() -> None:
    e = map_api_error(
        EdiApiError(400, "bad value s3cr3t-key-value here", "/x?key=s3cr3t-key-value"),
        secrets=["s3cr3t-key-value"],
    )
    assert "s3cr3t-key-value" not in e.message and "s3cr3t-key-value" not in str(e.details)
    assert redact("a KEY b", ["KEY", ""]) == "a *** b"


def test_auth_required_error_details() -> None:
    e = auth_required_error(tool="edi_get_lineage", endpoint="/package/sources/eml")
    assert e.code == "auth_required" and e.hint == "Read edi://guide/api-key."
    assert (
        e.details["tool"] == "edi_get_lineage" and e.details["endpoint"] == "/package/sources/eml"
    )


def test_payload_shape() -> None:
    assert ToolError("not_found", "m", details={"a": 1}, hint="h").to_payload() == {
        "error": {"code": "not_found", "message": "m", "details": {"a": 1}, "hint": "h"}
    }
    assert "hint" not in ToolError("invalid_argument", "m").to_payload()["error"]


def test_input_required_copies_its_inputs() -> None:
    schema = {"type": "object"}
    state = {"field": "x"}
    pending = InputRequired(key="k", message="pick", requested_schema=schema, state=state)
    schema["x"] = 1
    state["y"] = 2
    assert pending.requested_schema == {"type": "object"}
    assert pending.state == {"field": "x"}
