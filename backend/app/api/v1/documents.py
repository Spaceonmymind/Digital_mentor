import logging
import mimetypes
import zipfile
import json
from pathlib import Path, PurePath
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import FileResponse, Response

import fitz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Analysis, Document
from app.db.session import get_session
from app.schemas.documents import DocumentContentResponse, DocumentResponse
from app.services.extraction import TextExtractionService
from app.services.security import StubFileSecurityService
from app.services.storage import DocumentStorage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

PDF_MIME_TYPES = {"application/pdf"}
DOCX_MIME_TYPES = {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        name=document.original_name,
        mime_type=document.mime_type,
        size=document.size,
        status=document.status,
        created_at=document.created_at,
    )


async def _validate_upload(upload: UploadFile) -> tuple[str, str, bytes]:
    original_name = PurePath(upload.filename or "").name
    extension = PurePath(original_name).suffix.lower()
    if extension not in settings.allowed_file_types:
        raise AppError("UNSUPPORTED_FILE_TYPE", "Поддерживаются только PDF и DOCX")

    header = await upload.read(4096)
    await upload.seek(0)
    if not header:
        raise AppError("EMPTY_FILE", "Файл пуст")

    mime_type = upload.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    if extension == ".pdf":
        if mime_type not in PDF_MIME_TYPES:
            raise AppError("INVALID_MIME_TYPE", "MIME-тип PDF не совпадает с ожидаемым")
        if not header.startswith(b"%PDF"):
            raise AppError("INVALID_FILE_SIGNATURE", "Файл не похож на PDF")
    if extension == ".docx":
        if mime_type not in DOCX_MIME_TYPES:
            raise AppError("INVALID_MIME_TYPE", "MIME-тип DOCX не совпадает с ожидаемым")
        if not header.startswith(b"PK"):
            raise AppError("INVALID_FILE_SIGNATURE", "Файл DOCX не является ZIP-контейнером")

    return original_name, extension, mime_type


@router.post("", response_model=DocumentResponse)
async def upload_document(upload: UploadFile, session: AsyncSession = Depends(get_session)) -> DocumentResponse:
    original_name, extension, mime_type = await _validate_upload(upload)
    storage = DocumentStorage()
    stored = await storage.save(upload, extension)

    if stored.size == 0:
        storage.delete(stored.stored_name)
        raise AppError("EMPTY_FILE", "Файл пуст")
    if stored.size > settings.max_upload_size_bytes:
        storage.delete(stored.stored_name)
        raise AppError("FILE_TOO_LARGE", f"Размер файла превышает {settings.max_upload_size_mb} МБ", status_code=413)

    if extension == ".docx":
        try:
            with zipfile.ZipFile(stored.path) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise AppError("INVALID_DOCX_STRUCTURE", "Файл DOCX имеет некорректную структуру")
        except zipfile.BadZipFile as exc:
            storage.delete(stored.stored_name)
            raise AppError("INVALID_DOCX_STRUCTURE", "Файл DOCX не является корректным ZIP-контейнером") from exc

    scan_result = await StubFileSecurityService().scan(stored.path)
    document = Document(
        original_name=original_name,
        stored_name=stored.stored_name,
        mime_type=mime_type,
        size=stored.size,
        checksum=stored.checksum,
        storage_path=str(stored.path),
        status="uploaded",
        extraction_status="pending",
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)

    try:
        extracted_path = storage.extracted_path(document.id)
        TextExtractionService().extract(document.id, stored.path, extension, extracted_path)
        document.extracted_path = str(extracted_path)
        document.extraction_status = "completed"
        await session.commit()
        await session.refresh(document)
    except AppError:
        document.extraction_status = "failed"
        await session.commit()
        raise

    logger.info(
        "document_uploaded document_id=%s size=%s mime_type=%s scan_status=%s",
        document.id,
        document.size,
        document.mime_type,
        scan_result.status,
    )
    return _document_response(document)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str, session: AsyncSession = Depends(get_session)) -> DocumentResponse:
    document = await session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise AppError("DOCUMENT_NOT_FOUND", "Документ не найден", status_code=404)
    return _document_response(document)


@router.get("/{document_id}/content", response_model=DocumentContentResponse)
async def get_document_content(document_id: str, session: AsyncSession = Depends(get_session)) -> DocumentContentResponse:
    document = await session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise AppError("DOCUMENT_NOT_FOUND", "Документ не найден", status_code=404)
    if document.extraction_status != "completed" or not document.extracted_path:
        raise AppError("DOCUMENT_TEXT_NOT_FOUND", "Извлеченный текст документа не найден", status_code=404)

    path = DocumentStorage().extracted_directory(document_id) / "content.json"
    if not path.exists():
        raise AppError("DOCUMENT_TEXT_NOT_FOUND", "Извлеченный текст документа не найден", status_code=404)
    return DocumentContentResponse(document_id=document_id, content=json.loads(path.read_text(encoding="utf-8")))


@router.get("/{document_id}/source")
async def get_document_source(document_id: str, session: AsyncSession = Depends(get_session)) -> FileResponse:
    document = await session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise AppError("DOCUMENT_NOT_FOUND", "Документ не найден", status_code=404)
    path = Path(document.storage_path)
    if not path.exists():
        raise AppError("DOCUMENT_FILE_NOT_FOUND", "Исходный файл документа не найден", status_code=404)
    safe_name = PurePath(document.original_name).name
    return FileResponse(
        path,
        media_type=document.mime_type,
        filename=safe_name,
        content_disposition_type="inline",
    )


@router.get("/{document_id}/pages/{page_number}/preview")
async def get_document_page_preview(
    document_id: str,
    page_number: int,
    session: AsyncSession = Depends(get_session),
) -> Response:
    document = await session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise AppError("DOCUMENT_NOT_FOUND", "Документ не найден", status_code=404)
    if document.mime_type != "application/pdf":
        raise AppError("DOCUMENT_PREVIEW_UNSUPPORTED", "Постраничный просмотр доступен только для PDF", status_code=409)
    path = Path(document.storage_path)
    if not path.exists():
        raise AppError("DOCUMENT_FILE_NOT_FOUND", "Исходный файл документа не найден", status_code=404)
    try:
        with fitz.open(path) as pdf:
            if page_number < 1 or page_number > pdf.page_count:
                raise AppError("DOCUMENT_PAGE_NOT_FOUND", "Страница документа не найдена", status_code=404)
            page = pdf.load_page(page_number - 1)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
            payload = pixmap.tobytes("png")
    except AppError:
        raise
    except Exception as exc:
        raise AppError("DOCUMENT_PREVIEW_FAILED", "Не удалось подготовить страницу документа", status_code=500) from exc
    return Response(content=payload, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{document_id}", response_model=DocumentResponse)
async def delete_document(
    document_id: str,
    force: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    document = await session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise AppError("DOCUMENT_NOT_FOUND", "Документ не найден", status_code=404)

    active = (
        await session.execute(
            select(Analysis).where(
                Analysis.document_id == document_id,
                Analysis.status.in_(["queued", "processing"]),
            )
        )
    ).scalars().all()
    if active and not force:
        raise AppError("DOCUMENT_HAS_ACTIVE_ANALYSIS", "Сначала отмените активный анализ или используйте force=true", status_code=409)

    for analysis in active:
        analysis.status = "cancelled"
        analysis.error_message = "ANALYSIS_CANCELLED"

    storage = DocumentStorage()
    storage.delete(document.stored_name)
    storage.delete_tree(storage.extracted_directory(document_id))
    related_analyses = (
        await session.execute(select(Analysis).where(Analysis.document_id == document_id))
    ).scalars().all()
    for analysis in related_analyses:
        storage.delete_tree(storage.reports_dir / analysis.id)

    document.status = "deleted"
    document.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(document)
    logger.info("document_deleted document_id=%s", document.id)
    return _document_response(document)
