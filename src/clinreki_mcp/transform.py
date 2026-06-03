"""Чистые (без сети) преобразования ответов API в компактные структуры.

Здесь же — билдеры фильтров поиска. ВАЖНО: API молча игнорирует неизвестные
``fieldName`` (откатываясь к полному списку), поэтому собираем фильтры только
из проверенных полей: status, name, agecategory, mkbid, nkoid.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

_DATE_RE = re.compile(r"/Date\((\d+)\)/")


def parse_ms_date(value: Any) -> str | None:
    """'/Date(1751546455050)/' → ISO-8601. Для большинства полей есть готовый *Str."""
    if not value:
        return None
    match = _DATE_RE.search(str(value))
    if not match:
        return None
    return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=timezone.utc).isoformat()


def _date(item: dict[str, Any], str_field: str, ms_field: str) -> str | None:
    return item.get(str_field) or parse_ms_date(item.get(ms_field))


def map_search_item(item: dict[str, Any]) -> dict[str, Any]:
    """Элемент списка поиска → компактная запись (id = CodeVersion)."""
    return {
        "id": item.get("CodeVersion"),
        "code": item.get("Code"),
        "version": item.get("Version"),
        "name": (item.get("Name") or "").strip(),
        "publish_date": _date(item, "PublishDateStr", "PublishDate"),
        "age_category": item.get("AgeCategoryStr"),
        "status": item.get("Status"),
        "mkb_codes": [m.get("MkbCode") for m in item.get("Mkbs") or []],
        "developers": [
            d.get("NkoShortName") or d.get("NkoName") for d in item.get("Developers") or []
        ],
        "specialties": [s.get("ReferenceName") for s in item.get("Specialities") or []],
    }


def build_toc(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Оглавление документа из obj.sections[] (без самого текста)."""
    sections = (document.get("obj") or {}).get("sections") or []
    toc = []
    for i, section in enumerate(sections):
        content = section.get("content") or ""
        toc.append(
            {
                "index": i,
                "id": section.get("id"),
                "title": (section.get("title") or "").strip(),
                "content_length": len(content),
                "has_content": bool(content.strip()),
            }
        )
    return toc


def map_document_meta(
    document: dict[str, Any],
    nko_names: dict[int, str] | None = None,
    *,
    toc: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Документ КР → метаданные (без полного текста).

    ``nko_names`` — заранее разрешённые имена НКО для proff_associations.
    """
    nko_names = nko_names or {}
    meta = {
        "id": document.get("id"),
        "name": (document.get("name") or "").strip(),
        "code": document.get("code"),
        "version": document.get("ver") or document.get("version"),
        "mkb": document.get("mkb"),
        # В документе mkbs — список строк-кодов (в результатах поиска — список словарей).
        "mkb_codes": [
            (m if isinstance(m, str) else m.get("MkbCode")) for m in document.get("mkbs") or []
        ],
        "adult": document.get("adult"),
        "child": document.get("child"),
        "npc_approved": document.get("NPC_approved"),
        "publish_date": document.get("publish_date") or parse_ms_date(document.get("PublishDate")),
        "apply_status": document.get("apply_status"),
        "developers": [
            nko_names.get(nid, f"NkoId {nid}") for nid in document.get("proff_associations") or []
        ],
        # В документе specialities — словари {Id, Name} (в поиске — {ReferenceId, ReferenceName}).
        "specialities": [
            (s.get("Name") or s.get("ReferenceName")) if isinstance(s, dict) else s
            for s in document.get("specialities") or []
        ],
    }
    if toc is not None:
        meta["section_count"] = len(toc)
        meta["toc"] = toc
    return meta


# --- Билдеры фильтров (только проверенные поля) ---
def status_filter(value: int) -> dict[str, Any]:
    return {"fieldName": "status", "filterType": 1, "filterValueType": 2,
            "value1": value, "value2": "", "values": []}


def name_filter(value: str) -> dict[str, Any]:
    return {"fieldName": "name", "filterType": 2, "filterValueType": 1,
            "value1": value, "value2": "", "values": []}


def agecategory_filter(value: int) -> dict[str, Any]:
    return {"fieldName": "agecategory", "filterType": 1, "filterValueType": 2,
            "value1": value, "value2": "", "values": []}


def mkbid_filter(value: int) -> dict[str, Any]:
    return {"fieldName": "mkbid", "filterType": 1, "filterValueType": 2,
            "value1": value, "value2": "", "values": []}


def nkoid_filter(value: int) -> dict[str, Any]:
    return {"fieldName": "nkoid", "filterType": 1, "filterValueType": 2,
            "value1": value, "value2": "", "values": []}


def build_search_body(
    filters: list[dict[str, Any]],
    *,
    sort_field: str,
    sort_desc: bool,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    return {
        "filters": filters,
        "sortOption": {"fieldName": sort_field, "sortType": 2 if sort_desc else 1},
        "pageSize": page_size,
        "currentPage": page,
        "useANDoperator": True,
        "columns": [],
    }
