"""Справочные инструменты: список разработчиков (НКО) и специальностей."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP

from ..client import ClinrecApiError

if TYPE_CHECKING:
    from ..server import AppContext


def _app(ctx: Context) -> "AppContext":
    return ctx.request_context.lifespan_context


async def list_developers_impl(
    app: "AppContext", query: str | None = None, limit: int = 25
) -> dict[str, Any]:
    try:
        nko = await app.cache.nko()
        items = nko["flat"]
        if query:
            needle = query.strip().lower()
            items = [
                n
                for n in items
                if needle in (n.get("name") or "").lower()
                or needle in (n.get("shortname") or "").lower()
            ]
        limit = max(1, min(limit, 100))
        results = [
            {
                "id": n.get("Id"),
                "name": n.get("name"),
                "shortname": n.get("shortname"),
                "profile": n.get("profile"),
                "url": n.get("url"),
            }
            for n in items[:limit]
        ]
        return {"total": len(items), "returned": len(results), "results": results}
    except ClinrecApiError as exc:
        return {"error": str(exc)}


async def list_specialties_impl(app: "AppContext") -> dict[str, Any]:
    try:
        specialties = await app.cache.specialties()
        return {
            "total": len(specialties),
            "results": specialties,
            "note": (
                "Отдельного API нет; список собран из поля Specialities всех записей. "
                "Покрытие частичное."
            ),
        }
    except ClinrecApiError as exc:
        return {"error": str(exc)}


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_developers(ctx: Context, query: str | None = None, limit: int = 25) -> dict:
        """Список разработчиков (НКО). При query — фильтр по названию/аббревиатуре.

        Поле id можно передать в search_clinrecs(nko_id=...).
        """
        return await list_developers_impl(_app(ctx), query, limit)

    @mcp.tool()
    async def list_specialties(ctx: Context) -> dict:
        """Справочник специальностей (reference_id, name, count), агрегированный из записей.

        reference_id или name можно передать в search_clinrecs(specialty=...).
        """
        return await list_specialties_impl(_app(ctx))
