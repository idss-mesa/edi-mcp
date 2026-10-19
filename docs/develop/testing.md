---
title: "Testing"
description: "edi-mcp's hermetic test suite, the FixtureRouter that replays recorded PASTA and DataONE traffic, recording and checking fixtures, opt-in live tests, the coverage, type and lint gates, CI jobs and the documentation checks."
type: Guide
tags:
  - develop
  - testing
  - fixtures
  - ci
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: pytest
    resource: "https://docs.pytest.org/"
    title: "pytest documentation"
    author: "team:pytest"
  - id: ci
    resource: "https://github.com/idss-mesa/edi-mcp/blob/main/.github/workflows/ci.yml"
    title: "edi-mcp CI workflow"
    author: "team:idss-mesa"
status: stable
---

# Testing

```bash
uv sync --all-extras
uv run pytest                                   # hermetic unit + conformance tests
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run mypy --strict src
uv run python scripts/record_fixtures.py check  # fixtures carry no secrets
```

## Hermetic tests

`uv run pytest` makes no network calls: live tests are deselected by default
(`-m 'not live'`). Every upstream request goes through
`tests/fixture_router.py`, a stand-in for PASTA, the EDI auth service, DataONE
and the citation service, driven by `tests/fixtures/manifest.json`. The router:

* answers the auth service itself with fake JWTs for a test key, so no real
  token is ever stored;
* enforces PASTA's credential rules: no credential gets the recorded anonymous
  403, an unknown token or a wrong `?key=` gets 401;
* fails the test when a credential (cookie or `key`) reaches any host other
  than PASTA;
* records every request in `FixtureRouter.calls`, and fails the test on any
  request it has no fixture for.

Tool tests go through `tests.helpers.call_ok`, which asserts success and
validates the payload against the tool's `outputSchema`, and `call_err`, which
asserts an error code. The suite also covers the registry, config precedence,
log redaction, error mapping, the identifier parser (with hypothesis), the
cache, both backends, the transports (stdio in both protocol eras, Streamable
HTTP, `X-EDI-Key` passthrough, health endpoints) and MCP 2026-07-28
conformance (`tests/test_spec_conformance_2026_07_28.py`).

The coverage gate is 85% (`fail_under` in `pyproject.toml`, branch coverage):

```bash
uv run pytest --cov=edi_mcp --cov-report=term
```

## Recording fixtures

Fixtures come only from `scripts/record_fixtures.py`, never from hand edits.
`record` drives the real backends (PASTA with `EDI_API_KEY`, DataONE without)
and the scenarios in `TOOL_SCENARIOS` (real tool calls on both backends)
through a recording transport, so fixtures match the exact requests edi-mcp
makes:

```bash
set -a; . ./.env; set +a          # loads EDI_API_KEY without printing it
uv run python scripts/record_fixtures.py record
```

It never records auth-service traffic, stores no response headers except
`Content-Type` and `Location`, and scrubs every body before writing it: the
key, every `edi-token` it saw, anything JWT-shaped, and the identity claims
decoded from the token. Recordings land in the gitignored `tests/fixtures/_raw/`
and replace the committed set only if `check` passes on them.

`check` (run in CI on every push) fails on a JWT-shaped string, `edi-token=`,
`set-cookie`, `key=` in a manifest URL, the API key itself when `EDI_API_KEY` is
set, a missing manifest file, a fixture over 40 KB, or a total over 3 MB.

## Live tests

Live tests hit the real services and are opt-in. DataONE tests run anonymously;
PASTA tests also need `EDI_API_KEY` and skip without it.

```bash
set -a; . ./.env; set +a
EDI_MCP_LIVE=1 uv run pytest -m live tests/live
```

They assert behaviour that fixtures cannot: that sorted searches come back in
order (PASTA silently ignores a malformed sort, so an HTTP 200 proves nothing),
that bounding-box, author and temporal filters return the right region and
records, and that the dated scope snapshot is current (a known scope leaving
PASTA fails; new scopes only warn). DataONE's index changes without notice
(see `RESEARCH.md`), so a failing live test can mean upstream drift rather than
a regression.

## CI

`.github/workflows/ci.yml` runs on pushes to `main`, pull requests, manual
dispatch and nightly:

* **test** on Python 3.11, 3.12 and 3.13: ruff check and format, `mypy
  --strict`, the fixture `check`, and the full suite with coverage;
* **test (macOS)**: smoke and stdio transport tests on Python 3.12;
* **MCP 2026-07-28 conformance**: asserts the SDK is `mcp` 2.x, runs the
  conformance and transport tests, and fails on deprecated MCP features in
  `src/` (sampling, roots, `logging/setLevel`, the legacy SSE transport,
  session ids);
* **live smoke (nightly)**: on schedule and manual dispatch, with
  `EDI_MCP_LIVE=1` and the repository secret `EDI_API_KEY` (PASTA tests skip
  when the secret is not set).

## Documentation checks

`.github/workflows/docs.yml` validates the docs on every pull request and
deploys the site from `main`:

```bash
uv run python scripts/okf_validate.py docs      # OKF v0.2 frontmatter and reserved files
uv run python scripts/gen_llms_txt.py           # docs/llms.txt, docs/llms-full.txt
uv run python scripts/gen_tools_reference.py    # docs/tools/reference.md
uv run python scripts/gen_config_reference.py   # settings table in configuration.md
git diff --exit-code docs/                      # CI fails if a generated file drifted
uv run zensical build --clean --strict          # broken links fail the build
```
