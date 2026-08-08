import json
import zipfile
from pathlib import Path

import fitz
from docx import Document as DocxDocument

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
            page_text = page.get_text("text").strip()
            if page_text:
                full_text_parts.append(page_text)
            pages.append({"page_number": page_index, "text": page_text, "blocks": blocks})

        full_text = "\n\n".join(full_text_parts).strip()
        if not full_text:
            raise AppError("DOCUMENT_TEXT_NOT_FOUND", "В PDF не найден текстовый слой", status_code=422)

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
            "full_text": full_text,
        }
