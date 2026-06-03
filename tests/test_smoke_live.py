"""Опциональные «дымовые» тесты против реального API.

По умолчанию отключены (addopts = -m 'not live'). Запуск: ``uv run pytest -m live``.
"""

from __future__ import annotations

import httpx
import pytest

from clinreki_mcp.cache import ReferenceCache
from clinreki_mcp.client import ClinrecApiClient
from clinreki_mcp.constants import BASE_URL
from clinreki_mcp.server import AppContext
from clinreki_mcp.tools.clinrecs import (
    get_clinrec_impl,
    get_clinrec_section_impl,
    search_clinrecs_impl,
)

pytestmark = pytest.mark.live


def _live_app() -> AppContext:
    client = httpx.AsyncClient(
        base_url=BASE_URL,
        timeout=httpx.Timeout(120.0, connect=10.0),
        headers={"User-Agent": "clinreki-mcp-tests", "Accept": "application/json"},
    )
    api = ClinrecApiClient(client)
    return AppContext(api=api, cache=ReferenceCache(api))


async def test_live_search_and_document():
    app = _live_app()
    found = await search_clinrecs_impl(app, name="косоглазие")
    assert found["total"] >= 1
    code_version = found["results"][0]["id"]

    doc = await get_clinrec_impl(app, code_version)
    assert doc["name"]
    assert doc["section_count"] > 0

    # резолв кода МКБ
    by_mkb = await search_clinrecs_impl(app, mkb_code="H50.0")
    assert "error" not in by_mkb

    # первый раздел с содержимым -> markdown
    section_id = next(s["id"] for s in doc["toc"] if s["has_content"])
    section = await get_clinrec_section_impl(app, code_version, section_id=section_id)
    assert section["total_length"] > 0


async def test_live_total_records():
    app = _live_app()
    res = await search_clinrecs_impl(app, page_size=1)
    assert res["total"] and res["total"] > 1000  # ~1798 без фильтров
