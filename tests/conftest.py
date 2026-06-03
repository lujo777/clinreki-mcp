"""Общие фикстуры: образцы ответов API и фабрика AppContext на MockTransport."""

from __future__ import annotations

from typing import Any, Callable

import httpx
import pytest

from clinreki_mcp.cache import ReferenceCache
from clinreki_mcp.client import ClinrecApiClient
from clinreki_mcp.constants import BASE_URL
from clinreki_mcp.server import AppContext

# 1×1 прозрачный PNG в base64 — для проверки разбора картинок.
PNG_1x1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def mkb_raw() -> list[dict[str, Any]]:
    return [
        {"Id": 1, "ParentId": None, "Name": "Инфекционные болезни", "Code": "A00-B99", "IsGroup": True},
        {"Id": 3512, "ParentId": 1, "Name": "Содружественное косоглазие", "Code": "H50", "IsGroup": True},
        {"Id": 3513, "ParentId": 3512, "Name": "Сходящееся косоглазие", "Code": "H50.0", "IsGroup": False},
        {"Id": 3514, "ParentId": 3512, "Name": "Расходящееся косоглазие", "Code": "H50.1", "IsGroup": False},
    ]


@pytest.fixture
def nko_envelope() -> dict[str, Any]:
    return {
        "d": {
            "success": True,
            "data": [
                {"Id": 1, "name": "Ассоциация сердечно-сосудистых хирургов", "shortname": "АССХ",
                 "profile": "хирургия", "url": "https://racvs.ru"},
                {"Id": 12, "name": "Общество офтальмологов России", "shortname": "ООР",
                 "profile": "офтальмология", "url": ""},
            ],
        }
    }


@pytest.fixture
def search_item() -> dict[str, Any]:
    return {
        "Id": 1920,
        "Name": "Косоглазие содружественное ",
        "PublishDate": "/Date(1751546455050)/",
        "PublishDateStr": "2025-07-03T15:40:55",
        "Code": 922,
        "Version": 1,
        "CodeVersion": "922_1",
        "Status": 0,
        "AgeCategory": 3,
        "AgeCategoryStr": "Взрослые, дети",
        "Developers": [{"NkoId": 12, "NkoName": "Общество офтальмологов России", "NkoShortName": "ООР"}],
        "Mkbs": [
            {"MkbId": 3513, "MkbCode": "H50.0", "MkbName": "Сходящееся косоглазие"},
            {"MkbId": 3514, "MkbCode": "H50.1", "MkbName": "Расходящееся косоглазие"},
        ],
        "Specialities": [{"ReferenceId": 50, "ReferenceName": "Офтальмология"}],
    }


@pytest.fixture
def document() -> dict[str, Any]:
    return {
        "db_id": 1920,
        "id": "922_1",
        "name": "Косоглазие содружественное",
        "mkb": "H50.0/H50.1",
        "code": 922,
        "ver": 2,
        "version": 1,
        "adult": True,
        "child": True,
        "NPC_approved": True,
        "proff_associations": [12],
        "publish_date": "2025-07-03T15:40:55",
        "apply_status": "Применяется",
        # В документе (GetClinrec2) mkbs — строки-коды, а specialities — словари {Id, Name}.
        "mkbs": ["H50.0", "H50.1"],
        "specialities": [{"Id": 50, "Name": "Офтальмология"}],
        "obj": {
            "sections": [
                {"id": "doc_abbreviation", "title": "Список сокращений",
                 "content": "<p>АКС – аномальная корреспонденция сетчаток</p>"
                            "<p>ЦНС – центральная нервная система</p>"},
                {"id": "doc_criteria", "title": "Критерии оценки качества",
                 "content": "<table><thead><tr><th><p>№</p></th><th><p>Критерий</p></th></tr></thead>"
                            "<tbody><tr><td><p>1.</p></td><td><p>Осмотр офтальмолога</p></td></tr>"
                            "</tbody></table>"},
                {"id": "doc_b", "title": "Приложение Б",
                 "content": f'<p>Алгоритм</p><img src="data:image/png;base64,{PNG_1x1}" alt="Схема">'},
            ]
        },
    }


@pytest.fixture
def default_handler(mkb_raw, nko_envelope, document, search_item) -> Callable:
    def handler(request: httpx.Request) -> httpx.Response:
        op = request.url.params.get("op")
        if op == "GetMkbRefList":
            return httpx.Response(200, json=mkb_raw)
        if op == "GetNkoList":
            return httpx.Response(200, json=nko_envelope)
        if op == "GetClinrec2":
            return httpx.Response(200, json=document)
        if op == "GetJsonClinrecsFilterV2":
            return httpx.Response(
                200,
                json={"Data": [search_item], "CurrentPage": 1, "PageSize": 1,
                      "TotalRecords": 1, "Erorrs": None},
            )
        return httpx.Response(404, json={})

    return handler


@pytest.fixture
def app_factory() -> Callable[[Callable], AppContext]:
    """Фабрика AppContext поверх httpx.MockTransport (без реальной сети)."""

    def factory(handler: Callable) -> AppContext:
        client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
        api = ClinrecApiClient(client, base_delay=0.0)  # без задержек в тестах
        return AppContext(api=api, cache=ReferenceCache(api))

    return factory
