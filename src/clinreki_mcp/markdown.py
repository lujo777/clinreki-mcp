"""Преобразование HTML разделов КР в читаемый Markdown с разбором картинок.

Картинки в документах встроены как base64-data-URI прямо в HTML
(``<img src="data:image/png;base64,...">``) и могут весить сотни КБ —
инлайнить их в текст нельзя. Поэтому при конвертации каждая картинка
выносится из текста: на её место ставится компактный плейсхолдер, а сама
картинка попадает в манифест (только метаданные) и доступна отдельным
инструментом как изображение, которое модель может «увидеть».
"""

from __future__ import annotations

import base64
import re
from typing import Any

from markdownify import markdownify as _markdownify

_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_SRC_RE = re.compile(r"""src\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_ALT_RE = re.compile(r"""alt\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_DATAURI_RE = re.compile(r"^data:(?P<mt>[^;,]+)?(?P<b64>;base64)?,(?P<data>.*)$", re.DOTALL)


def _parse_data_uri(src: str) -> tuple[str | None, bytes | None]:
    """Из data-URI вернуть (media_type, bytes) или (None, None)."""
    match = _DATAURI_RE.match((src or "").strip())
    if not match or not match.group("b64"):
        return None, None
    media_type = match.group("mt") or "application/octet-stream"
    try:
        return media_type, base64.b64decode(match.group("data"))
    except (ValueError, base64.binascii.Error):
        return media_type, None


def html_to_markdown(
    html: str, code_version: str, section_id: str | None
) -> tuple[str, list[dict[str, Any]]]:
    """HTML раздела → (markdown, манифест картинок).

    Манифест: ``[{index, section_id, media_type, size_bytes, alt}]``.
    ``index`` нумеруется внутри раздела; вместе с ``section_id`` однозначно
    адресует картинку для ``get_clinrec_image``.
    """
    images: list[dict[str, Any]] = []
    tokens: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        src_m = _SRC_RE.search(tag)
        alt_m = _ALT_RE.search(tag)
        alt = alt_m.group(1) if alt_m else ""
        media_type, data = _parse_data_uri(src_m.group(1)) if src_m else (None, None)
        idx = len(images)
        images.append(
            {
                "index": idx,
                "section_id": section_id,
                "media_type": media_type,
                "size_bytes": len(data) if data is not None else None,
                "alt": alt,
            }
        )
        # Чисто буквенно-цифровой маркер не искажается markdownify; подменим после.
        token = f"IMGPLACEHOLDERTOKEN{idx}X"
        label = alt or f"Рисунок {idx + 1}"
        tokens[token] = (
            f'[{label} — изображение; получить через '
            f'get_clinrec_image(code_version="{code_version}", '
            f'section_id="{section_id}", image_index={idx})]'
        )
        return token

    cleaned = _IMG_RE.sub(_replace, html or "")
    md = _markdownify(cleaned, heading_style="ATX", bullets="-")
    for token, text in tokens.items():
        md = md.replace(token, text)
    md = re.sub(r"\n{3,}", "\n\n", md).strip()
    return md, images


def extract_image_data(html: str, image_index: int) -> tuple[bytes, str] | None:
    """Найти ``image_index``-ю картинку в HTML и вернуть (bytes, media_type)."""
    tags = _IMG_RE.findall(html or "")
    if image_index < 0 or image_index >= len(tags):
        return None
    src_m = _SRC_RE.search(tags[image_index])
    if not src_m:
        return None
    media_type, data = _parse_data_uri(src_m.group(1))
    if data is None:
        return None
    return data, media_type or "application/octet-stream"
