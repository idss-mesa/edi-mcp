from __future__ import annotations

import pytest

from edi_mcp.errors import ToolError
from edi_mcp.prompts import get_prompt, list_prompts
from edi_mcp.server import EdiServer
from tests.helpers.asgi import AppHarness, rpc


def test_listing() -> None:
    prompts = list_prompts()
    assert [p.name for p in prompts] == ["edi_cite_package", "edi_find_data", "edi_plan_download"]
    required = {p.name: [a.name for a in p.arguments or [] if a.required] for p in prompts}
    assert required == {
        "edi_cite_package": ["package"],
        "edi_find_data": ["question"],
        "edi_plan_download": ["package"],
    }


def text(name: str, args: dict[str, str]) -> str:
    content = get_prompt(name, args).messages[0].content
    return content.text  # type: ignore[union-attr]


def test_rendering() -> None:
    find = text(
        "edi_find_data",
        {"question": "How does NPP respond to drought?", "place": "Jornada", "years": "1990-2010"},
    )
    assert "How does NPP respond to drought?" in find and "Place: Jornada" in find
    assert "start_year=1990, end_year=2010" in find and "edi_search_packages" in find
    assert "ORed" in find
    one_year = text("edi_find_data", {"question": "q", "years": "2004"})
    assert "start_year=2004, end_year=2004" in one_year and "Place" not in one_year
    assert "edi_search_packages." in text("edi_find_data", {"question": "q"})
    cite = text("edi_cite_package", {"package": "knb-lter-hbr.14.22", "style": "bibtex"})
    assert "style='BIBTEX'" in cite and "edi_get_citation(package='knb-lter-hbr.14.22'" in cite
    assert "style='ESIP'" in text("edi_cite_package", {"package": "x.1.1"})
    plan = text("edi_plan_download", {"package": "knb-lter-hbr.14.22", "entities": "a, b,"})
    assert "entities=['a', 'b']" in plan and "edi_download_entities" in plan
    assert "never overwrites" in plan and "needs a key" in plan
    assert "entities=" not in text("edi_plan_download", {"package": "x.1.1"})


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("edi_find_data", {}),
        ("edi_find_data", {"question": "q", "years": "the nineties"}),
        ("edi_cite_package", {"package": "x", "bogus": "1"}),
        ("edi_cite_package", {"package": "x", "style": "APA"}),
        ("edi_plan_download", {"package": "  "}),
        ("edi_nope", {}),
    ],
)
def test_validation(name: str, args: dict[str, str]) -> None:
    with pytest.raises(ToolError):
        get_prompt(name, args)


async def test_prompts_over_http(http_server: EdiServer) -> None:
    async with AppHarness(http_server) as client:
        _, listing = await rpc(client, "prompts/list")
        _, got = await rpc(
            client, "prompts/get", {"name": "edi_cite_package", "arguments": {"package": "x.1.1"}}
        )
        _, bad = await rpc(client, "prompts/get", {"name": "edi_cite_package", "arguments": {}})
    assert listing["result"]["cacheScope"] == "public" and len(listing["result"]["prompts"]) == 3
    assert got["result"]["messages"][0]["role"] == "user"
    assert bad["error"]["code"] == -32602 and bad["error"]["data"]["code"] == "invalid_argument"
