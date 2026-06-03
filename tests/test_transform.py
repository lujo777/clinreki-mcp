"""Тесты чистых преобразований и билдеров фильтров."""

from __future__ import annotations

from clinreki_mcp.transform import (
    agecategory_filter,
    build_search_body,
    build_toc,
    map_document_meta,
    map_search_item,
    mkbid_filter,
    name_filter,
    nkoid_filter,
    parse_ms_date,
    status_filter,
)


def test_parse_ms_date():
    iso = parse_ms_date("/Date(1751546455050)/")
    assert iso is not None and iso.startswith("2025-07-03")
    assert parse_ms_date(None) is None
    assert parse_ms_date("не дата") is None


def test_map_search_item(search_item):
    mapped = map_search_item(search_item)
    assert mapped["id"] == "922_1"
    assert mapped["code"] == 922
    assert mapped["name"] == "Косоглазие содружественное"
    assert mapped["mkb_codes"] == ["H50.0", "H50.1"]
    assert mapped["developers"] == ["ООР"]
    assert mapped["specialties"] == ["Офтальмология"]
    # Предпочитаем готовое строковое поле даты.
    assert mapped["publish_date"] == "2025-07-03T15:40:55"


def test_build_toc(document):
    toc = build_toc(document)
    assert [s["id"] for s in toc] == ["doc_abbreviation", "doc_criteria", "doc_b"]
    assert all(s["has_content"] for s in toc)
    assert toc[0]["index"] == 0


def test_map_document_meta(document):
    meta = map_document_meta(document, {12: "Общество офтальмологов России"}, toc=build_toc(document))
    assert meta["id"] == "922_1"
    assert meta["version"] == 2  # ver имеет приоритет над version
    assert meta["developers"] == ["Общество офтальмологов России"]
    assert meta["section_count"] == 3
    assert meta["mkb_codes"] == ["H50.0", "H50.1"]  # строки-коды из документа
    assert meta["specialities"] == ["Офтальмология"]  # словари {Id, Name}


def test_filter_builders_use_only_validated_fields():
    assert status_filter(0)["fieldName"] == "status"
    assert name_filter("кос") == {
        "fieldName": "name", "filterType": 2, "filterValueType": 1,
        "value1": "кос", "value2": "", "values": [],
    }
    assert agecategory_filter(2)["value1"] == 2
    assert mkbid_filter(3513)["fieldName"] == "mkbid"
    assert nkoid_filter(12)["fieldName"] == "nkoid"


def test_build_search_body():
    body = build_search_body([name_filter("x")], sort_field="name", sort_desc=False, page=2, page_size=5)
    assert body["sortOption"] == {"fieldName": "name", "sortType": 1}
    assert body["currentPage"] == 2 and body["pageSize"] == 5
    assert body["useANDoperator"] is True
