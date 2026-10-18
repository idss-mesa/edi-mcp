"""Identifier parsing (DESIGN.md D9)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from edi_mcp.edi.pid import Doi, PackageId, parse_reference
from edi_mcp.errors import ToolError

MD5 = "2017345f0977c0f7c46e1ad90ce1b062"
ENTITY = "c4f72fa0cb155f1b61f1333bb67e3d00"


@pytest.mark.parametrize(
    ("value", "scope", "identifier", "revision", "form"),
    [
        ("knb-lter-hbr.14.22", "knb-lter-hbr", 14, 22, "package-id"),
        ("  knb-lter-hbr/14/22 ", "knb-lter-hbr", 14, 22, "package-id"),
        ("knb-lter-hbr.14.21.xml", "knb-lter-hbr", 14, 21, "package-id"),
        ("edi.2081", "edi", 2081, None, "package-id"),
        ("knb-lter-jrn.210548103.newest", "knb-lter-jrn", 210548103, "newest", "package-id"),
        (
            "https://portal.edirepository.org/nis/mapbrowse?scope=knb-lter-hbr&identifier=14&revision=22",
            "knb-lter-hbr",
            14,
            22,
            "portal-url",
        ),
        (
            "https://portal.edirepository.org/nis/mapbrowse?scope=edi&identifier=2081",
            "edi",
            2081,
            None,
            "portal-url",
        ),
        (
            "https://portal.edirepository.org/nis/metadataviewer?packageid=edi.2081.1",
            "edi",
            2081,
            1,
            "portal-url",
        ),
        (
            "https://pasta.lternet.edu/package/metadata/eml/knb-lter-hbr/14/22",
            "knb-lter-hbr",
            14,
            22,
            "pasta-url",
        ),
        (
            "https://pasta.lternet.edu/package/eml/knb-lter-hbr/14/newest",
            "knb-lter-hbr",
            14,
            "newest",
            "pasta-url",
        ),
        (
            "https://gmn.lternet.edu/mn/v2/object/https%3A%2F%2Fpasta.lternet.edu%2Fpackage"
            "%2Fmetadata%2Feml%2Fknb-lter-hbr%2F14%2F22",
            "knb-lter-hbr",
            14,
            22,
            "pasta-url",
        ),
    ],
)
def test_package_forms(
    value: str, scope: str, identifier: int, revision: object, form: str
) -> None:
    ref = parse_reference(value)
    assert ref.package is not None and ref.doi is None
    assert (ref.package.scope, ref.package.identifier, ref.revision, ref.form) == (
        scope,
        identifier,
        revision,
        form,
    )
    assert ref.needs_backend == (not isinstance(revision, int))


def test_entity_url_keeps_the_entity() -> None:
    ref = parse_reference(f"https://pasta.lternet.edu/package/data/eml/knb-lter-hbr/14/22/{ENTITY}")
    assert ref.package == PackageId("knb-lter-hbr", 14, 22) and ref.entity_id == ENTITY


@pytest.mark.parametrize(
    "value",
    [
        f"doi:10.6073/pasta/{MD5}",
        f"10.6073/pasta/{MD5.upper()}",
        f"https://doi.org/10.6073/pasta/{MD5}",
        f"http://dx.doi.org/10.6073/PASTA/{MD5}",
        f"https://gmn.lternet.edu/mn/v2/object/doi:10.6073%2Fpasta%2F{MD5}",
    ],
)
def test_doi_forms(value: str) -> None:
    ref = parse_reference(value)
    assert ref.doi == Doi(MD5) and ref.form == "doi" and ref.needs_backend
    assert ref.doi.pid == f"doi:10.6073/pasta/{MD5}"
    assert ref.doi.url == f"https://doi.org/10.6073/pasta/{MD5}"


@pytest.mark.parametrize(
    ("value", "why"),
    [
        ("", "empty"),
        ("streamflow", "expected"),
        ("doi:10.5061/dryad.abc", "only EDI DOIs"),
        ("https://example.org/page", "expected"),
        ("knb-lter-hbr.x.3", "expected"),
    ],
)
def test_invalid(value: str, why: str) -> None:
    with pytest.raises(ToolError) as exc:
        parse_reference(value)
    assert exc.value.code == "invalid_argument" and why in exc.value.message
    assert exc.value.hint == "Read edi://guide/package-identifiers."


def test_revision_argument() -> None:
    assert parse_reference("edi.2081", 1).package == PackageId("edi", 2081, 1)
    ref = parse_reference("edi.2081", "oldest")
    assert ref.revision == "oldest" and ref.package == PackageId("edi", 2081)
    assert parse_reference("edi.2081.1", 1).revision == 1
    with pytest.raises(ToolError, match="also given"):
        parse_reference("edi.2081.1", 2)
    assert parse_reference(f"doi:10.6073/pasta/{MD5}", 3).doi is not None


def test_package_id_properties() -> None:
    pkg = PackageId("knb-lter-hbr", 14)
    assert pkg.series == str(pkg) == "knb-lter-hbr.14" and pkg.path == "knb-lter-hbr/14"
    with pytest.raises(ValueError, match="no revision"):
        _ = pkg.package_id
    full = pkg.with_revision(22)
    assert full.package_id == str(full) == "knb-lter-hbr.14.22"
    assert full.path == "knb-lter-hbr/14/22"
    with pytest.raises(ValueError):
        PackageId("edi", -1)


scopes = st.from_regex(r"[a-z][a-z0-9-]{0,20}", fullmatch=True)
numbers = st.integers(min_value=0, max_value=10**9)


@given(scopes, numbers, numbers, st.sampled_from([".", "/"]))
def test_roundtrip(scope: str, identifier: int, revision: int, sep: str) -> None:
    ref = parse_reference(sep.join([scope, str(identifier), str(revision)]))
    assert ref.package == PackageId(scope, identifier, revision)
    assert parse_reference(ref.package.package_id).package == ref.package
    assert parse_reference(f"https://pasta.lternet.edu/package/eml/{ref.package.path}").package == (
        ref.package
    )


@given(st.text(max_size=80))
def test_never_crashes(text: str) -> None:
    try:
        parse_reference(text)
    except ToolError as exc:
        assert exc.code == "invalid_argument"
