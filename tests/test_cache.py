"""Тесты ленивых кэшей справочников."""

from __future__ import annotations

import httpx

from clinreki_mcp.cache import ReferenceCache
from clinreki_mcp.client import ClinrecApiClient
from clinreki_mcp.constants import BASE_URL


def _cache(handler) -> ReferenceCache:
    transport = httpx.MockTransport(handler)
    api = ClinrecApiClient(httpx.AsyncClient(base_url=BASE_URL, transport=transport), base_delay=0.0)
    return ReferenceCache(api)


async def test_resolve_mkb_code(default_handler):
    cache = _cache(default_handler)
    assert await cache.resolve_mkb_code("h50.0") == 3513  # регистронезависимо
    assert await cache.resolve_mkb_code("H50.1") == 3514
    assert await cache.resolve_mkb_code("НЕТ_ТАКОГО") is None


async def test_mkb_children_index(default_handler):
    cache = _cache(default_handler)
    mkb = await cache.mkb()
    children = mkb["children_of"].get(3512)
    assert {c["Code"] for c in children} == {"H50.0", "H50.1"}


async def test_nko_name(default_handler):
    cache = _cache(default_handler)
    assert await cache.nko_name(12) == "Общество офтальмологов России"
    assert await cache.nko_name(999) is None


async def test_mkb_loaded_once(default_handler):
    """Справочник МКБ грузится единожды (single-flight)."""
    calls = {"n": 0}

    def handler(request):
        if request.url.params.get("op") == "GetMkbRefList":
            calls["n"] += 1
        return default_handler(request)

    cache = _cache(handler)
    await cache.mkb()
    await cache.mkb()
    assert calls["n"] == 1


async def test_specialties_aggregated():
    records = [
        {"Specialities": [{"ReferenceId": 50, "ReferenceName": "Офтальмология"}]},
        {"Specialities": [{"ReferenceId": 50, "ReferenceName": "Офтальмология"}]},
        {"Specialities": [{"ReferenceId": 26, "ReferenceName": "Гематология"}]},
        {"Specialities": None},
    ]

    def handler(request):
        if request.url.params.get("op") == "GetJsonClinrecsFilterV2":
            return httpx.Response(200, json={"Data": records, "TotalRecords": len(records), "Erorrs": None})
        return httpx.Response(404, json={})

    cache = _cache(handler)
    specs = await cache.specialties()
    assert specs[0] == {"reference_id": 50, "name": "Офтальмология", "count": 2}
    assert {s["reference_id"] for s in specs} == {50, 26}
