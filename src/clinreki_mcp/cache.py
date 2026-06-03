"""Ленивые кэши справочных данных (МКБ, НКО, полный список записей).

Справочники меняются редко, а МКБ весит ~3.2 МБ, поэтому грузим их лениво
(не на старте сервера) и единожды, защищая загрузку ``asyncio.Lock`` —
конкурирующие первые вызовы не вызовут двойной запрос.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .client import ClinrecApiClient


def _norm_code(code: str | None) -> str:
    return (code or "").strip().upper()


class ReferenceCache:
    def __init__(self, api: ClinrecApiClient):
        self._api = api
        self._mkb_lock = asyncio.Lock()
        self._nko_lock = asyncio.Lock()
        self._records_lock = asyncio.Lock()
        self._mkb: dict[str, Any] | None = None
        self._nko: dict[str, Any] | None = None
        self._records: list[dict[str, Any]] | None = None
        self._specialties: list[dict[str, Any]] | None = None

    # --- МКБ-10 ---
    async def mkb(self) -> dict[str, Any]:
        if self._mkb is None:
            async with self._mkb_lock:
                if self._mkb is None:
                    raw = await self._api.get_mkb_raw()
                    by_id: dict[Any, dict[str, Any]] = {}
                    by_code: dict[str, dict[str, Any]] = {}
                    children_of: dict[Any, list[dict[str, Any]]] = {}
                    for node in raw:
                        by_id[node.get("Id")] = node
                        code = _norm_code(node.get("Code"))
                        # Код→узел: коды уникальны; на всякий случай берём первый.
                        if code and code not in by_code:
                            by_code[code] = node
                        children_of.setdefault(node.get("ParentId"), []).append(node)
                    self._mkb = {
                        "by_id": by_id,
                        "by_code": by_code,
                        "children_of": children_of,
                        "flat": raw,
                    }
        return self._mkb

    async def resolve_mkb_code(self, code: str) -> int | None:
        """Преобразовать код МКБ-10 (например 'H50.0') во внутренний MkbId."""
        mkb = await self.mkb()
        node = mkb["by_code"].get(_norm_code(code))
        return node.get("Id") if node else None

    # --- НКО (разработчики) ---
    async def nko(self) -> dict[str, Any]:
        if self._nko is None:
            async with self._nko_lock:
                if self._nko is None:
                    raw = await self._api.get_nko_raw()
                    self._nko = {"by_id": {n.get("Id"): n for n in raw}, "flat": raw}
        return self._nko

    async def nko_name(self, nko_id: int) -> str | None:
        nko = await self.nko()
        node = nko["by_id"].get(nko_id)
        if not node:
            return None
        return node.get("name") or node.get("shortname")

    # --- Полный список записей / специальности ---
    async def records(self) -> list[dict[str, Any]]:
        if self._records is None:
            async with self._records_lock:
                if self._records is None:
                    self._records = await self._api.get_all_records()
        return self._records

    async def specialties(self) -> list[dict[str, Any]]:
        """Справочник специальностей, агрегированный из поля Specialities всех записей.

        Отдельного endpoint у API нет, поэтому собираем уникальные
        {ReferenceId, ReferenceName} и считаем, у скольких КР они встречаются.
        """
        if self._specialties is None:
            agg: dict[Any, dict[str, Any]] = {}
            for item in await self.records():
                for sp in item.get("Specialities") or []:
                    rid = sp.get("ReferenceId")
                    if rid is None:
                        continue
                    entry = agg.setdefault(
                        rid, {"reference_id": rid, "name": sp.get("ReferenceName"), "count": 0}
                    )
                    entry["count"] += 1
            self._specialties = sorted(
                agg.values(), key=lambda e: (-e["count"], e["name"] or "")
            )
        return self._specialties
