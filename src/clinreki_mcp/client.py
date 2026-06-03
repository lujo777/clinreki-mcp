"""HTTP-клиент к API клинических рекомендаций.

Один общий ``httpx.AsyncClient`` (пул соединений) с ретраями и экспоненциальным
бэкоффом на временные сбои, плюс централизованный разбор поля ошибок поиска.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from .constants import (
    ALL_RECORDS_PAGE_SIZE,
    API_PATH,
    OP_DOCUMENT,
    OP_MKB,
    OP_NKO,
    OP_SEARCH,
)

# Коды, которые имеет смысл повторить (временные сбои шлюза).
RETRYABLE_STATUS = {502, 503, 504}


class ClinrecApiError(Exception):
    """Ошибка обращения к API клинических рекомендаций."""

    def __init__(self, message: str, *, op: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.op = op
        self.status_code = status_code


class ClinrecApiClient:
    """Тонкая обёртка над общим ``httpx.AsyncClient``."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_attempts: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
    ):
        self._client = client
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay

    async def _sleep(self, attempt: int) -> None:
        delay = min(self._base_delay * (2 ** (attempt - 1)), self._max_delay)
        if delay > 0:
            delay += random.uniform(0, delay * 0.25)  # джиттер
            await asyncio.sleep(delay)

    async def _request(
        self,
        method: str,
        op: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        read_timeout: float | None = None,
    ) -> Any:
        query = {"op": op, **(params or {})}
        timeout: httpx.Timeout | None = None
        if read_timeout is not None:
            timeout = httpx.Timeout(read_timeout, connect=10.0, write=30.0, pool=10.0)

        last_exc: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                kwargs: dict[str, Any] = {"params": query}
                if json is not None:
                    kwargs["json"] = json
                if timeout is not None:
                    kwargs["timeout"] = timeout
                resp = await self._client.request(method, API_PATH, **kwargs)

                if resp.status_code in RETRYABLE_STATUS and attempt < self._max_attempts:
                    await self._sleep(attempt)
                    continue
                resp.raise_for_status()

                try:
                    return resp.json()
                except ValueError as exc:
                    raise ClinrecApiError(
                        f"Не удалось разобрать JSON-ответ (op={op}): {exc}",
                        op=op,
                        status_code=resp.status_code,
                    ) from exc

            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt < self._max_attempts:
                    await self._sleep(attempt)
                    continue
                raise ClinrecApiError(
                    f"Сетевая ошибка при запросе к API (op={op}): {exc}", op=op
                ) from exc
            except httpx.HTTPStatusError as exc:
                # 4xx и невосстановимые статусы — не ретраим.
                raise ClinrecApiError(
                    f"HTTP {exc.response.status_code} от API (op={op})",
                    op=op,
                    status_code=exc.response.status_code,
                ) from exc

        raise ClinrecApiError(f"Не удалось выполнить запрос (op={op})", op=op) from last_exc

    async def search(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST ?op=GetJsonClinrecsFilterV2 — поиск/список КР."""
        data = await self._request("POST", OP_SEARCH, json=body)
        if isinstance(data, dict):
            # ВНИМАНИЕ: в API ключ ошибок реально называется "Erorrs" (опечатка).
            # Проверяем сначала его, затем — на случай исправления — "Errors".
            errors = data.get("Erorrs") or data.get("Errors")
            if errors:
                raise ClinrecApiError(f"API вернул ошибку поиска: {errors}", op=OP_SEARCH)
        return data

    async def get_document(self, code_version: str) -> dict[str, Any]:
        """GET ?op=GetClinrec2 — полный документ КР (может весить несколько МБ)."""
        return await self._request(
            "GET", OP_DOCUMENT, params={"id": code_version, "ssid": "null"}, read_timeout=120.0
        )

    async def get_mkb_raw(self) -> list[dict[str, Any]]:
        """GET ?op=GetMkbRefList — справочник МКБ-10 целиком (~3.2 МБ)."""
        data = await self._request("GET", OP_MKB, read_timeout=120.0)
        return data if isinstance(data, list) else []

    async def get_nko_raw(self) -> list[dict[str, Any]]:
        """GET ?op=GetNkoList — список разработчиков, развёрнутый из {d:{data:[...]}}."""
        data = await self._request("GET", OP_NKO)
        envelope = data.get("d") if isinstance(data, dict) else None
        if not envelope or not envelope.get("success"):
            raise ClinrecApiError("GetNkoList вернул success=false", op=OP_NKO)
        return envelope.get("data") or []

    async def get_all_records(self) -> list[dict[str, Any]]:
        """Весь список КР одним запросом (для справочника специальностей и клиентских фильтров)."""
        body = {
            "filters": [],
            "sortOption": {"fieldName": "name", "sortType": 1},
            "pageSize": ALL_RECORDS_PAGE_SIZE,
            "currentPage": 1,
            "useANDoperator": True,
            "columns": [],
        }
        data = await self.search(body)
        return data.get("Data") or []
