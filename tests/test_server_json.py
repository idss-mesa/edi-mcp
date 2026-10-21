"""server.json (MCP Registry entry) is valid and agrees with the package."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import jsonschema

from edi_mcp import __version__

ROOT = Path(__file__).resolve().parents[1]
# Vendored from https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json
SCHEMA = Path(__file__).parent / "data" / "server.schema.json"


def _load(path: Path) -> dict:  # type: ignore[type-arg]
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_server_json_validates_and_matches_the_package() -> None:
    server = _load(ROOT / "server.json")
    schema = _load(SCHEMA)
    assert server["$schema"].endswith("/2025-12-11/server.schema.json")
    jsonschema.validate(server, schema)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    (package,) = server["packages"]
    assert server["version"] == package["version"] == __version__
    assert package["registryType"] == "pypi" and package["identifier"] == project["name"]
    assert project["name"] in project["scripts"]  # `uvx <identifier>` finds a command
    env = {v["name"]: v for v in package["environmentVariables"]}
    assert env["EDI_API_KEY"]["isSecret"] is True and env["EDI_API_KEY"]["isRequired"] is False


def test_readme_carries_the_registry_ownership_marker() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    name = _load(ROOT / "server.json")["name"]
    assert f"<!-- mcp-name: {name} -->" in readme.splitlines()
