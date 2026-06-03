"""Инструменты по клиническим рекомендациям: поиск, документ, разделы, картинки.

Логика вынесена в ``*_impl``-функции (принимают ``AppContext``), чтобы её можно
было тестировать напрямую; ``register`` лишь оборачивает их тонкими
``@mcp.tool()``-функциями, извлекающими контекст.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP, Image

from ..client import ClinrecApiError
from ..constants import (
    AGE_CATEGORY,
    ALL_RECORDS_PAGE_SIZE,
    DEFAULT_SECTION_CHARS,
    MAX_PAGE_SIZE,
    MAX_SECTION_CHARS,
)
from ..markdown import extract_image_data, html_to_markdown
from ..transform import (
    agecategory_filter,
    build_search_body,
    build_toc,
    map_document_meta,
    map_search_item,
    mkbid_filter,
    name_filter,
    nkoid_filter,
    status_filter,
)

if TYPE_CHECKING:
    from ..server import AppContext


def _app(ctx: Context) -> "AppContext":
    return ctx.request_context.lifespan_context


def _sections(document: dict[str, Any]) -> list[dict[str, Any]]:
    return (document.get("obj") or {}).get("sections") or []


def _section_index(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"index": i, "id": s.get("id"), "title": s.get("title")} for i, s in enumerate(sections)]


def _paginate(content: str, offset: int, max_chars: int) -> dict[str, Any]:
    total = len(content)
    max_chars = max(1, min(max_chars, MAX_SECTION_CHARS))
    offset = max(0, offset)
    chunk = content[offset : offset + max_chars]
    truncated = offset + max_chars < total
    return {
        "total_length": total,
        "offset": offset,
        "returned_length": len(chunk),
        "truncated": truncated,
        "next_offset": offset + max_chars if truncated else None,
        "content": chunk,
    }


async def _filter_by_specialty(
    app: "AppContext",
    specialty: str,
    filters: list[dict[str, Any]],
    *,
    sort_field: str,
    sort_desc: bool,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """Клиентская фильтрация по специальности (API её не поддерживает).

    Берём большую страницу с применёнными серверными фильтрами и отбираем
    записи, у которых в Specialities есть нужный ReferenceId или подстрока имени.
    """
    body = build_search_body(
        filters, sort_field=sort_field, sort_desc=sort_desc, page=1, page_size=ALL_RECORDS_PAGE_SIZE
    )
    data = await app.api.search(body)
    needle = specialty.strip().lower()
    matched = []
    for item in data.get("Data") or []:
        for sp in item.get("Specialities") or []:
            name = (sp.get("ReferenceName") or "").lower()
            if needle == str(sp.get("ReferenceId")) or needle in name:
                matched.append(item)
                break
    start = (page - 1) * page_size
    page_items = matched[start : start + page_size]
    return {
        "total": len(matched),
        "page": page,
        "page_size": page_size,
        "returned": len(page_items),
        "results": [map_search_item(it) for it in page_items],
        "note": "Фильтр по специальности применён на стороне клиента; покрытие данных частичное.",
    }


async def search_clinrecs_impl(
    app: "AppContext",
    *,
    name: str | None = None,
    mkb_code: str | None = None,
    age_category: str | None = None,
    specialty: str | None = None,
    nko_id: int | None = None,
    status: int | None = None,
    sort_field: str = "publishdate",
    sort_desc: bool = True,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    try:
        filters: list[dict[str, Any]] = []
        if status is not None:
            filters.append(status_filter(status))
        if name:
            filters.append(name_filter(name))
        if age_category is not None:
            key = age_category.strip().lower()
            if key not in AGE_CATEGORY:
                return {"error": f"age_category должно быть одним из {list(AGE_CATEGORY)}"}
            filters.append(agecategory_filter(AGE_CATEGORY[key]))
        if mkb_code:
            mkbid = await app.cache.resolve_mkb_code(mkb_code)
            if mkbid is None:
                return {"error": f"Код МКБ '{mkb_code}' не найден", "total": 0, "results": []}
            filters.append(mkbid_filter(mkbid))
        if nko_id is not None:
            filters.append(nkoid_filter(nko_id))

        page = max(1, page)
        page_size = max(1, min(page_size, MAX_PAGE_SIZE))

        if specialty:
            return await _filter_by_specialty(
                app, specialty, filters, sort_field=sort_field, sort_desc=sort_desc,
                page=page, page_size=page_size,
            )

        body = build_search_body(
            filters, sort_field=sort_field, sort_desc=sort_desc, page=page, page_size=page_size
        )
        data = await app.api.search(body)
        results = [map_search_item(it) for it in data.get("Data") or []]
        return {
            "total": data.get("TotalRecords"),
            "page": data.get("CurrentPage"),
            "page_size": data.get("PageSize"),
            "returned": len(results),
            "results": results,
        }
    except ClinrecApiError as exc:
        return {"error": str(exc)}


async def get_clinrec_impl(
    app: "AppContext", code_version: str, include_toc: bool = True
) -> dict[str, Any]:
    try:
        doc = await app.api.get_document(code_version)
        if not isinstance(doc, dict) or not (doc.get("name") or _sections(doc)):
            return {"error": f"Документ '{code_version}' не найден"}
        nko_names = {
            nid: (await app.cache.nko_name(nid) or f"NkoId {nid}")
            for nid in doc.get("proff_associations") or []
        }
        toc = build_toc(doc) if include_toc else None
        return map_document_meta(doc, nko_names, toc=toc)
    except ClinrecApiError as exc:
        return {"error": str(exc)}


async def get_clinrec_section_impl(
    app: "AppContext",
    code_version: str,
    *,
    section_id: str | None = None,
    section_title: str | None = None,
    index: int | None = None,
    output_format: str = "markdown",
    max_chars: int = DEFAULT_SECTION_CHARS,
    offset: int = 0,
) -> dict[str, Any]:
    try:
        doc = await app.api.get_document(code_version)
        sections = _sections(doc)
        if not sections:
            return {"error": f"В документе '{code_version}' нет разделов"}

        provided = [section_id is not None, section_title is not None, index is not None]
        if sum(provided) != 1:
            return {
                "error": "Укажите ровно один селектор: section_id | section_title | index",
                "available_sections": _section_index(sections),
            }

        section = None
        if section_id is not None:
            section = next((s for s in sections if s.get("id") == section_id), None)
        elif index is not None:
            if 0 <= index < len(sections):
                section = sections[index]
        else:
            matches = [
                s for s in sections if section_title.lower() in (s.get("title") or "").lower()
            ]
            if len(matches) > 1:
                return {
                    "error": "Найдено несколько разделов; уточните section_title или используйте section_id",
                    "candidates": [{"id": s.get("id"), "title": s.get("title")} for s in matches],
                }
            section = matches[0] if matches else None

        if section is None:
            return {"error": "Раздел не найден", "available_sections": _section_index(sections)}

        html = section.get("content") or ""
        images: list[dict[str, Any]] = []
        if output_format == "html":
            content = html
        else:  # markdown | text — оба отдаём как читаемый markdown
            content, images = html_to_markdown(html, code_version, section.get("id"))

        result = {
            "id": section.get("id"),
            "title": (section.get("title") or "").strip(),
            "format": output_format,
            "images": images,
        }
        result.update(_paginate(content, offset, max_chars))
        return result
    except ClinrecApiError as exc:
        return {"error": str(exc)}


async def get_clinrec_markdown_impl(
    app: "AppContext", code_version: str, max_chars: int = DEFAULT_SECTION_CHARS, offset: int = 0
) -> dict[str, Any]:
    try:
        doc = await app.api.get_document(code_version)
        sections = _sections(doc)
        if not sections:
            return {"error": f"В документе '{code_version}' нет разделов"}

        parts: list[str] = []
        images: list[dict[str, Any]] = []
        for section in sections:
            title = (section.get("title") or "").strip()
            html = section.get("content") or ""
            if not html.strip() and not title:
                continue
            md, imgs = html_to_markdown(html, code_version, section.get("id"))
            images.extend(imgs)
            parts.append(f"## {title}\n\n{md}".strip() if title else md)

        full = "\n\n".join(parts).strip()
        result = {
            "id": doc.get("id"),
            "name": (doc.get("name") or "").strip(),
            "images": images,
        }
        result.update(_paginate(full, offset, max_chars))
        return result
    except ClinrecApiError as exc:
        return {"error": str(exc)}


async def get_clinrec_image_impl(
    app: "AppContext",
    code_version: str,
    image_index: int,
    section_id: str | None = None,
    save_path: str | None = None,
):
    try:
        doc = await app.api.get_document(code_version)
        sections = _sections(doc)
        if section_id is not None:
            section = next((s for s in sections if s.get("id") == section_id), None)
            if section is None:
                return {"error": f"Раздел '{section_id}' не найден"}
            html = section.get("content") or ""
        else:
            html = "".join(s.get("content") or "" for s in sections)

        extracted = extract_image_data(html, image_index)
        if extracted is None:
            return {"error": "Картинка не найдена по указанному индексу"}
        data, media_type = extracted

        if save_path:
            with open(save_path, "wb") as handle:
                handle.write(data)
            return {"saved_to": save_path, "media_type": media_type, "size_bytes": len(data)}

        image_format = media_type.split("/")[-1] if "/" in media_type else "png"
        return Image(data=data, format=image_format)
    except ClinrecApiError as exc:
        return {"error": str(exc)}


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def search_clinrecs(
        ctx: Context,
        name: str | None = None,
        mkb_code: str | None = None,
        age_category: str | None = None,
        specialty: str | None = None,
        nko_id: int | None = None,
        status: int | None = None,
        sort_field: str = "publishdate",
        sort_desc: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Поиск клинических рекомендаций с фильтрами и пагинацией.

        Параметры:
        - name: поиск по подстроке в названии.
        - mkb_code: код МКБ-10 (например "H50.0"); разрешается во внутренний id.
        - age_category: "adult" | "child" | "both".
        - specialty: имя специальности или её reference_id (клиентский фильтр,
          покрытие частичное; см. list_specialties).
        - nko_id: id разработчика (см. list_developers).
        - status: рабочий статус записи; по умолчанию (None) возвращаются ВСЕ записи.
        - sort_field: "publishdate" | "name"; sort_desc: по убыванию (True).
        - page (с 1), page_size (1..50).

        В результатах поле id (= CodeVersion) используется в get_clinrec/_section/_markdown.
        """
        return await search_clinrecs_impl(
            _app(ctx), name=name, mkb_code=mkb_code, age_category=age_category,
            specialty=specialty, nko_id=nko_id, status=status, sort_field=sort_field,
            sort_desc=sort_desc, page=page, page_size=page_size,
        )

    @mcp.tool()
    async def get_clinrec(ctx: Context, code_version: str, include_toc: bool = True) -> dict:
        """Метаданные и оглавление одной КР по id (CodeVersion, например "922_1").

        Возвращает название, код/версию, МКБ, возрастные группы, разработчиков
        (имена НКО) и оглавление разделов (id, заголовок, длина). Полный текст НЕ
        возвращается — используйте get_clinrec_section или get_clinrec_markdown.
        """
        return await get_clinrec_impl(_app(ctx), code_version, include_toc)

    @mcp.tool()
    async def get_clinrec_section(
        ctx: Context,
        code_version: str,
        section_id: str | None = None,
        section_title: str | None = None,
        index: int | None = None,
        output_format: str = "markdown",
        max_chars: int = DEFAULT_SECTION_CHARS,
        offset: int = 0,
    ) -> dict:
        """Один раздел КР как читаемый Markdown (таблицы → GFM, картинки → плейсхолдеры).

        Укажите ровно один селектор: section_id (стабильный якорь, напр. "doc_diag_2_4"),
        section_title (подстрока заголовка) или index (с 0). output_format:
        "markdown" (по умолчанию) | "text" | "html". Большие разделы отдаются
        кусками: max_chars (≤50000) и offset; при truncated=true берите next_offset.
        Картинки перечислены в images[] (метаданные) и доступны через get_clinrec_image.
        """
        return await get_clinrec_section_impl(
            _app(ctx), code_version, section_id=section_id, section_title=section_title,
            index=index, output_format=output_format, max_chars=max_chars, offset=offset,
        )

    @mcp.tool()
    async def get_clinrec_markdown(
        ctx: Context,
        code_version: str,
        max_chars: int = DEFAULT_SECTION_CHARS,
        offset: int = 0,
    ) -> dict:
        """Весь документ КР, собранный в один Markdown (с пагинацией max_chars/offset).

        Заголовки разделов оформлены как "## ...". Картинки вынесены в images[]
        и доступны через get_clinrec_image. При truncated=true продолжайте с next_offset.
        """
        return await get_clinrec_markdown_impl(_app(ctx), code_version, max_chars, offset)

    @mcp.tool()
    async def get_clinrec_image(
        ctx: Context,
        code_version: str,
        image_index: int,
        section_id: str | None = None,
        save_path: str | None = None,
    ):
        """Вернуть картинку КР как изображение (модель сможет её увидеть).

        image_index — индекс картинки в пределах раздела (section_id) или, если
        section_id не задан, сквозной индекс по всему документу. Если указать
        save_path — картинка сохраняется в файл, а в ответе возвращается путь.
        """
        return await get_clinrec_image_impl(
            _app(ctx), code_version, image_index, section_id=section_id, save_path=save_path
        )
