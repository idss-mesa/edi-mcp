"""The fixture recorder's scrubber and checker (CLAUDE.md security rules)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from scripts.record_fixtures import Scrubber, check, fixture_name
from tests.fixture_router import ANONYMOUS_403, FIXTURES, manifest_key


def _jwt(claims: dict[str, object]) -> str:
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJSUzI1NiJ9.{payload}.c2lnbmF0dXJl"


def test_committed_fixtures_pass_the_check() -> None:
    assert check(FIXTURES) == []


def test_scrubber_removes_token_identity_and_jwt_shapes() -> None:
    token = _jwt(
        {
            "sub": "EDI-0123456789abcdef0123456789abcdef01234567",
            "cn": "Ada Lovelace",
            "email": "ada@example.org",
            "principals": ["Public Access", "uid=ada,o=EDI,dc=edirepository,dc=org"],
        }
    )
    scrubber = Scrubber(["the-api-key-value"])
    scrubber.add_token_claims(token)
    text = (
        f"key the-api-key-value cookie {token} user EDI-0123456789abcdef0123456789abcdef01234567 "
        "Ada Lovelace ada@example.org uid=ada,o=EDI,dc=edirepository,dc=org Public Access "
        "and a stray eyJzdHJheQ.eyJ4IjoxfQ.sig"
    )
    clean = scrubber.scrub(text)
    for secret in ("the-api-key-value", "Ada Lovelace", "ada@example.org", "uid=ada", "eyJ"):
        assert secret not in clean
    assert "Public Access" in clean  # system principals are not identities
    assert scrubber.leaks(clean) == []
    assert scrubber.leaks(text)


def test_scrubber_ignores_garbage_tokens() -> None:
    not_claims = "x." + base64.urlsafe_b64encode(b"[1]").decode() + ".y"
    scrubber = Scrubber()
    scrubber.add_token_claims("not.a-jwt")
    scrubber.add_token_claims(not_claims)
    assert scrubber.secrets == {"not.a-jwt", not_claims}


def _write(directory: Path, entries: list[dict[str, object]], files: dict[str, str]) -> None:
    for name, text in files.items():
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text(text)
    (directory / "manifest.json").write_text(json.dumps(entries))


def test_check_flags_every_leak_class(tmp_path: Path) -> None:
    anon = {
        "key": ANONYMOUS_403.removeprefix("anon:"),
        "status": 403,
        "credential": False,
        "file": "pasta/403.txt",
    }
    _write(
        tmp_path,
        [
            anon,
            {"key": "GET pasta.lternet.edu/x?key=abc", "status": 200, "credential": True},
            {"key": "GET cn.dataone.org/y", "status": 200, "file": "cn/missing.json"},
        ],
        {
            "pasta/403.txt": "User 'x' is not authorized",
            "pasta/jwt.txt": "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abc",
            "pasta/cookie.txt": "Set-Cookie: edi-token=abc",
            "big.txt": "x" * (41 * 1024),
        },
    )
    problems = "\n".join(check(tmp_path, Scrubber(["s3cr3t-key"])))
    assert "credential parameter" in problems
    assert "cn/missing.json is missing" in problems
    assert "JWT-shaped" in problems and "edi-token or set-cookie" in problems
    assert "big.txt" in problems and "not referenced" in problems


def test_check_requires_manifest_and_anonymous_403(tmp_path: Path) -> None:
    assert check(tmp_path) == ["manifest.json: missing"]
    _write(tmp_path, [], {})
    assert any("anonymous PASTA 403" in p for p in check(tmp_path))


def test_fixture_names_are_readable_and_distinct() -> None:
    key = (
        "GET gmn.lternet.edu/mn/v2/object/https%3A%2F%2Fpasta.lternet.edu%2Fpackage"
        "%2Fmetadata%2Feml%2Fknb-lter-hbr%2F14%2F22"
    )
    name = fixture_name(key, 200, "text/xml; charset=utf-8")
    assert name.startswith("gmn/metadata_eml_knb_lter_hbr_14_22_200_") and name.endswith(".xml")
    anon = manifest_key("GET pasta.lternet.edu/package/eml", False)
    assert anon == ANONYMOUS_403
    assert fixture_name(anon, 403, None) != fixture_name(anon[5:], 403, None)
