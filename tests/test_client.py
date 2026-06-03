"""Тесты HTTP-клиента: ретраи, обработка Erorrs, отсутствие ретраев на 4xx."""

from __future__ import annotations

import httpx
import pytest

from clinreki_mcp.client import ClinrecApiClient, ClinrecApiError
from clinreki_mcp.constants import BASE_URL


def _client(handler) -> ClinrecApiClient:
    transport = httpx.MockTransport(handler)
    return ClinrecApiClient(httpx.AsyncClient(base_url=BASE_URL, transport=transport), base_delay=0.0)


async def test_search_raises_on_erorrs():
    def handler(_request):
        return httpx.Response(200, json={"Data": [], "Erorrs": "что-то пошло не так"})

    with pytest.raises(ClinrecApiError):
        await _client(handler).search({"filters": []})


async def test_retry_then_success():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"Data": [], "TotalRecords": 0, "Erorrs": None})

    data = await _client(handler).search({"filters": []})
    assert data["TotalRecords"] == 0
    assert calls["n"] == 3  # две неудачи + успех


async def test_no_retry_on_4xx():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(400, json={})

    with pytest.raises(ClinrecApiError):
        await _client(handler).search({"filters": []})
    assert calls["n"] == 1  # 4xx не ретраится


async def test_nko_success_false_raises():
    def handler(_request):
        return httpx.Response(200, json={"d": {"success": False, "data": []}})

    with pytest.raises(ClinrecApiError):
        await _client(handler).get_nko_raw()
