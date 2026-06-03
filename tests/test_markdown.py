"""Тесты HTML→Markdown и разбора картинок."""

from __future__ import annotations

from clinreki_mcp.markdown import extract_image_data, html_to_markdown


def test_table_converted_to_markdown(document):
    section = document["obj"]["sections"][1]  # doc_criteria
    md, images = html_to_markdown(section["content"], "922_1", "doc_criteria")
    assert "<table" not in md  # HTML вычищен
    assert "Критерий" in md and "Осмотр офтальмолога" in md
    assert "|" in md  # markdownify рендерит GFM-таблицу
    assert images == []


def test_image_extracted_not_inlined(document):
    section = document["obj"]["sections"][2]  # doc_b с base64-картинкой
    md, images = html_to_markdown(section["content"], "922_1", "doc_b")
    # base64 не попадает в текст
    assert "base64" not in md and "data:image" not in md
    # плейсхолдер ссылается на инструмент получения картинки
    assert "get_clinrec_image" in md
    assert "Алгоритм" in md
    assert len(images) == 1
    img = images[0]
    assert img["index"] == 0
    assert img["section_id"] == "doc_b"
    assert img["media_type"] == "image/png"
    assert img["size_bytes"] and img["size_bytes"] > 0
    assert img["alt"] == "Схема"


def test_extract_image_data(document):
    html = document["obj"]["sections"][2]["content"]
    extracted = extract_image_data(html, 0)
    assert extracted is not None
    data, media_type = extracted
    assert media_type == "image/png"
    assert data[:8] == b"\x89PNG\r\n\x1a\n"  # сигнатура PNG
    assert extract_image_data(html, 1) is None  # картинки с индексом 1 нет
