---
title: "Contributing"
description: "Branch and pull-request rules, the checks to run before pushing, the design and research records, the two change logs, documentation updates and versioning for edi-mcp."
type: Policy
tags:
  - develop
  - contributing
  - releases
generated:
  by: "claude/opus-5.5"
  at: "2026-10-19T00:00:00Z"
sources:
  - id: keepachangelog
    resource: "https://keepachangelog.com/en/1.1.0/"
    title: "Keep a Changelog 1.1.0"
    author: "team:keepachangelog"
  - id: semver
    resource: "https://semver.org/"
    title: "Semantic Versioning"
    author: "team:semver"
  - id: okf-spec
    resource: "https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md"
    title: "Open Knowledge Format (OKF) v0.2 specification"
    author: "team:google-cloud"
status: stable
---

# Contributing

1. Branch from `main` and open a pull request. One change per pull request;
   CI must be green before it is merged.
2. Before pushing, run the same checks CI runs:

    ```bash
    uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
    uv run mypy --strict src
    uv run pytest
    uv run python scripts/record_fixtures.py check
    ```

    If the change touches upstream behaviour, also run the live tests with a key
    (see [Testing](testing.md)).
3. Never commit `.env`, a key, an `edi-token`, or a fixture that did not come
   from `scripts/record_fixtures.py record`.

## Design and research records

* `DESIGN.md` keeps the decision register. Each decision has a D-number (D1
  hybrid backend, D2 bad keys, D4 credential form, D9 identifiers, …) with the
  question, the decision and the reason. Changing behaviour that a decision
  covers means updating that row in the same pull request; code comments cite
  the D-number.
* `RESEARCH.md` records verified EDI, DataONE and MCP facts with the date each
  was checked. PASTA and DataONE change without notice, so a new upstream fact
  goes in with its date, and a fact that stopped being true is corrected rather
  than deleted silently.
* `CLAUDE.md` and the code map summarise both for coding agents; keep them in
  step.

## Two change logs

* `CHANGELOG.md` (repository root) is the package release log, in the Keep a
  Changelog format[^keepachangelog]. Add user-visible changes under
  `[Unreleased]`.
* `docs/log.md` is the documentation bundle's log. Every docs change adds a
  dated `## YYYY-MM-DD` entry naming the pages created or updated.

## Documentation

The `docs/` tree is an Open Knowledge Format (OKF v0.2)[^okf-spec] bundle built
with Zensical. Content pages carry YAML frontmatter (`title`, `description`,
`type`, `tags`, `generated`, `sources`, `status`); section `index.md` files carry
none. After changing docs or tools:

```bash
uv run python scripts/gen_tools_reference.py    # when a tool changed
uv run python scripts/gen_config_reference.py   # when a setting changed
uv run python scripts/gen_llms_txt.py           # always: docs/llms.txt, docs/llms-full.txt
uv run python scripts/okf_validate.py docs
uv run zensical build --clean --strict
```

Commit the generated files; the docs workflow fails when they drift from their
sources. Pages may only state what the code on `main` does; tools that are not
merged yet belong on the [Roadmap](../tools/roadmap.md).

## Versioning

edi-mcp follows Semantic Versioning[^semver]. The version lives in
`src/edi_mcp/__init__.py`. The first release, v0.1.0, and its release workflow
are planned for build step 7.

[^keepachangelog]: Keep a Changelog 1.1.0. <https://keepachangelog.com/en/1.1.0/>
[^semver]: Semantic Versioning. <https://semver.org/>
[^okf-spec]: Open Knowledge Format (OKF) v0.2 specification. <https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md>
