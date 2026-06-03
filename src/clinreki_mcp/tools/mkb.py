"""Инструменты по справочнику МКБ-10 (поиск и навигация по дереву).

Сырьё GetMkbRefList — это ~3.2 МБ / 12 794 узла, поэтому наружу отдаются только
результаты поиска и обхода дерева, но не весь справочник.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP

from ..client import ClinrecApiError

if TYPE_CHECKING:
    from ..server import AppContext


def _app(ctx: Context) -> "AppContext":
    return ctx.request_context.lifespan_context


def _node(node: dict[str, Any] | None) -> dict[str, Any] | None:
    if not node:
        return None
    return {
        "id": node.get("Id"),
        "code": node.get("Code"),
        "name": node.get("Name"),
        "is_group": node.get("IsGroup"),
        "parent_id": node.get("ParentId"),
    }


async def search_mkb_impl(app: "AppContext", query: str, limit: int = 25) -> dict[str, Any]:
    try:
        needle = (query or "").strip().lower()
        if not needle:
            return {"error": "Параметр query не должен быть пустым"}
        limit = max(1, min(limit, 50))
        mkb = await app.cache.mkb()
        children_of = mkb["children_of"]

        matches = [
            node
            for node in mkb["flat"]
            if (node.get("Code") or "").lower().startswith(needle)
            or needle in (node.get("Name") or "").lower()
        ]
        results = []
        for node in matches[:limit]:
            entry = _node(node)
            entry["has_children"] = bool(children_of.get(node.get("Id")))
            results.append(entry)
        return {"total_matches": len(matches), "returned": len(results), "results": results}
    except ClinrecApiError as exc:
        return {"error": str(exc)}


async def get_mkb_children_impl(app: "AppContext", node_id: int) -> dict[str, Any]:
    try:
        mkb = await app.cache.mkb()
        children_of = mkb["children_of"]
        parent = mkb["by_id"].get(node_id)
        children = []
        for node in children_of.get(node_id) or []:
            entry = _node(node)
            entry["has_children"] = bool(children_of.get(node.get("Id")))
            children.append(entry)
        if parent is None and not children:
            return {"error": f"Узел МКБ с id={node_id} не найден"}
        return {"parent": _node(parent), "children": children, "count": len(children)}
    except ClinrecApiError as exc:
        return {"error": str(exc)}


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def search_mkb(ctx: Context, query: str, limit: int = 25) -> dict:
        """Поиск по справочнику МКБ-10 по префиксу кода или подстроке названия.

        Возвращает узлы {id, code, name, is_group, parent_id, has_children} и
        total_matches. id/code можно передать в search_clinrecs(mkb_code=...),
        а id — в get_mkb_children для обхода дерева.
        """
        return await search_mkb_impl(_app(ctx), query, limit)

    @mcp.tool()
    async def get_mkb_children(ctx: Context, node_id: int) -> dict:
        """Дочерние узлы заданного узла МКБ-10 (навигация по дереву)."""
        return await get_mkb_children_impl(_app(ctx), node_id)
