import json
import zipfile
from pathlib import Path

import fitz
from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from app.core.errors import AppError


class TextExtractionService:
    def extract(self, document_id: str, file_path: Path, extension: str, output_path: Path) -> dict:
        if extension == ".pdf":
            payload = self._extract_pdf(document_id, file_path)
        elif extension == ".docx":
            payload = self._extract_docx(document_id, file_path)
        else:
            raise AppError("UNSUPPORTED_FILE_TYPE", "Поддерживаются только PDF и DOCX")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def _extract_pdf(self, document_id: str, file_path: Path) -> dict:
        try:
            doc = fitz.open(file_path)
        except Exception as exc:
            raise AppError("DOCUMENT_CORRUPTED", "PDF-документ поврежден или не может быть открыт", status_code=422) from exc

        pages = []
        full_text_parts = []
        for page_index, page in enumerate(doc, start=1):
            blocks = []
            for block_index, block in enumerate(page.get_text("blocks")):
                x0, y0, x1, y1, text, *_ = block
                text = text.strip()
                if not text:
                    continue
                blocks.append(
                    {
                        "block_index": block_index,
                        "text": text,
                        "bbox": [float(x0), float(y0), float(x1), float(y1)],
                    }
                )
            page_text = "\n".join(block["text"] for block in blocks).strip()
            if page_text:
                full_text_parts.append(page_text)
            pages.append({"page_number": page_index, "text": page_text, "blocks": blocks})

        full_text = "\n\n".join(full_text_parts).strip()
        if not full_text:
            doc.close()
            raise AppError("DOCUMENT_TEXT_NOT_FOUND", "В PDF не найден текстовый слой", status_code=422)

        doc.close()

        return {
            "document_id": document_id,
            "page_count": len(pages),
            "pages": pages,
            "full_text": full_text,
        }

    def _extract_docx(self, document_id: str, file_path: Path) -> dict:
        try:
            with zipfile.ZipFile(file_path) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise AppError("INVALID_DOCX_STRUCTURE", "Файл DOCX имеет некорректную структуру")
        except zipfile.BadZipFile as exc:
            raise AppError("INVALID_DOCX_STRUCTURE", "Файл DOCX не является корректным ZIP-контейнером") from exc

        try:
            doc = DocxDocument(file_path)
        except Exception as exc:
            raise AppError("DOCUMENT_CORRUPTED", "DOCX-документ поврежден или не может быть открыт", status_code=422) from exc

        paragraphs = []
        full_text_parts = []
        for index, paragraph in enumerate(doc.paragraphs):
            text = paragraph.text.strip()
            if not text:
                continue
            paragraphs.append(
                {
                    "paragraph_index": index,
                    "style": paragraph.style.name if paragraph.style else None,
                    "text": text,
                    "formatting": self._paragraph_formatting(paragraph),
                }
            )
            full_text_parts.append(text)

        full_text = "\n\n".join(full_text_parts).strip()
        if not full_text:
            raise AppError("DOCUMENT_TEXT_NOT_FOUND", "В DOCX не найден текст", status_code=422)

        return {
            "document_id": document_id,
            "paragraph_count": len(paragraphs),
            "paragraphs": paragraphs,
            "document_formatting": {
                "sections": [self._section_formatting(section) for section in doc.sections],
                "tables": [self._table_metadata(table, index) for index, table in enumerate(doc.tables)],
                "header_footer_fields": self._header_footer_fields(doc),
                "pagination_reliable": False,
            },
            "full_text": full_text,
        }

    @staticmethod
    def _paragraph_formatting(paragraph) -> dict:
        fmt = paragraph.paragraph_format
        alignment_names = {
            WD_ALIGN_PARAGRAPH.LEFT: "left",
            WD_ALIGN_PARAGRAPH.CENTER: "center",
            WD_ALIGN_PARAGRAPH.RIGHT: "right",
            WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
        }
        runs = []
        for run in paragraph.runs:
            if not run.text.strip():
                continue
            runs.append(
                {
                    "text": run.text,
                    "font": run.font.name,
                    "font_size_pt": round(run.font.size.pt, 2) if run.font.size else None,
                    "bold": run.bold,
                    "italic": run.italic,
                }
            )
        return {
            "alignment": alignment_names.get(paragraph.alignment),
            "line_spacing": float(fmt.line_spacing) if isinstance(fmt.line_spacing, (int, float)) else None,
            "space_before_pt": round(fmt.space_before.pt, 2) if fmt.space_before else None,
            "space_after_pt": round(fmt.space_after.pt, 2) if fmt.space_after else None,
            "first_line_indent_mm": round(fmt.first_line_indent.mm, 2) if fmt.first_line_indent else None,
            "keep_with_next": fmt.keep_with_next,
            "page_break_before": fmt.page_break_before,
            "runs": runs,
        }

    @staticmethod
    def _section_formatting(section) -> dict:
        return {
            "page_width_mm": round(section.page_width.mm, 2),
            "page_height_mm": round(section.page_height.mm, 2),
            "top_margin_mm": round(section.top_margin.mm, 2),
            "bottom_margin_mm": round(section.bottom_margin.mm, 2),
            "left_margin_mm": round(section.left_margin.mm, 2),
            "right_margin_mm": round(section.right_margin.mm, 2),
        }

    @staticmethod
    def _table_metadata(table, index: int) -> dict:
        rows = []
        empty_cells = []
        for row_index, row in enumerate(table.rows):
            values = []
            for column_index, cell in enumerate(row.cells):
                value = cell.text.strip()
                values.append(value)
                if not value:
                    empty_cells.append({"row": row_index, "column": column_index})
            rows.append(values)
        return {
            "table_index": index,
            "row_count": len(table.rows),
            "column_count": len(table.columns),
            "rows": rows,
            "empty_cells": empty_cells,
            "style": table.style.name if table.style else None,
        }

    @staticmethod
    def _header_footer_fields(doc) -> list[str]:
        fields = set()
        for section in doc.sections:
            for container in (section.header, section.footer):
                for instruction in container._element.iter(qn("w:instrText")):
                    value = (instruction.text or "").strip()
                    if value:
                        fields.add(value)
        return sorted(fields)
