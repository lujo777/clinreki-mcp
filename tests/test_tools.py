"""Тесты инструментов (через *_impl, в обход MCP-транспорта)."""

from __future__ import annotations

import httpx
from mcp.server.fastmcp import Image

from clinreki_mcp.tools.clinrecs import (
    get_clinrec_image_impl,
    get_clinrec_impl,
    get_clinrec_markdown_impl,
    get_clinrec_section_impl,
    search_clinrecs_impl,
)
from clinreki_mcp.tools.mkb import get_mkb_children_impl, search_mkb_impl
from clinreki_mcp.tools.refs import list_developers_impl, list_specialties_impl


async def test_search_basic(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await search_clinrecs_impl(app, name="косоглазие")
    assert res["total"] == 1
    assert res["results"][0]["id"] == "922_1"


async def test_search_by_mkb_code_resolves(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await search_clinrecs_impl(app, mkb_code="H50.0")
    assert res["results"][0]["id"] == "922_1"


async def test_search_unknown_mkb_code(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await search_clinrecs_impl(app, mkb_code="ZZ9.9")
    assert "error" in res and res["total"] == 0


async def test_search_invalid_age(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await search_clinrecs_impl(app, age_category="старики")
    assert "error" in res


async def test_search_by_specialty_clientside(app_factory):
    records = [
        {"CodeVersion": "1_1", "Name": "A", "Specialities": [{"ReferenceId": 50, "ReferenceName": "Офтальмология"}]},
        {"CodeVersion": "2_1", "Name": "B", "Specialities": [{"ReferenceId": 26, "ReferenceName": "Гематология"}]},
    ]

    def handler(request):
        if request.url.params.get("op") == "GetJsonClinrecsFilterV2":
            return httpx.Response(200, json={"Data": records, "TotalRecords": 2, "Erorrs": None})
        return httpx.Response(404, json={})

    app = app_factory(handler)
    res = await search_clinrecs_impl(app, specialty="Гематология")
    assert res["total"] == 1
    assert res["results"][0]["id"] == "2_1"
    assert "note" in res


async def test_get_clinrec_meta_and_toc(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await get_clinrec_impl(app, "922_1")
    assert res["name"] == "Косоглазие содружественное"
    assert res["developers"] == ["Общество офтальмологов России"]  # resolved from [12]
    assert res["section_count"] == 3
    assert res["toc"][1]["id"] == "doc_criteria"


async def test_get_section_markdown(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await get_clinrec_section_impl(app, "922_1", section_id="doc_criteria")
    assert res["id"] == "doc_criteria"
    assert "Осмотр офтальмолога" in res["content"]
    assert "<table" not in res["content"]
    assert res["images"] == []


async def test_get_section_with_image(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await get_clinrec_section_impl(app, "922_1", section_id="doc_b")
    assert len(res["images"]) == 1
    assert "base64" not in res["content"]


async def test_get_section_requires_one_selector(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await get_clinrec_section_impl(app, "922_1")
    assert "error" in res and "available_sections" in res


async def test_get_section_by_title_substring(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await get_clinrec_section_impl(app, "922_1", section_title="сокращ")
    assert res["id"] == "doc_abbreviation"


async def test_section_truncation(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await get_clinrec_section_impl(app, "922_1", section_id="doc_abbreviation", max_chars=10)
    assert res["truncated"] is True
    assert res["next_offset"] == 10
    assert res["returned_length"] == 10


async def test_get_markdown_full_document(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await get_clinrec_markdown_impl(app, "922_1")
    assert res["id"] == "922_1"
    assert "## Критерии оценки качества" in res["content"]
    assert len(res["images"]) == 1


async def test_get_image_returns_image(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await get_clinrec_image_impl(app, "922_1", 0, section_id="doc_b")
    assert isinstance(res, Image)


async def test_get_image_save_to_disk(app_factory, default_handler, tmp_path):
    app = app_factory(default_handler)
    target = tmp_path / "scheme.png"
    res = await get_clinrec_image_impl(app, "922_1", 0, section_id="doc_b", save_path=str(target))
    assert res["saved_to"] == str(target)
    assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


async def test_search_mkb(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await search_mkb_impl(app, "H50")
    codes = {r["code"] for r in res["results"]}
    assert {"H50", "H50.0", "H50.1"} <= codes


async def test_get_mkb_children(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await get_mkb_children_impl(app, 3512)
    assert res["count"] == 2
    assert res["parent"]["code"] == "H50"


async def test_list_developers(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await list_developers_impl(app, query="офтальмолог")
    assert res["total"] == 1
    assert res["results"][0]["id"] == 12


async def test_list_specialties(app_factory, default_handler):
    app = app_factory(default_handler)
    res = await list_specialties_impl(app)
    assert res["total"] == 1
    assert res["results"][0]["name"] == "Офтальмология"
