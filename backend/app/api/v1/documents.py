import logging
import mimetypes
import zipfile
from pathlib import PurePath

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Document
from app.db.session import get_session
from app.schemas.documents import DocumentResponse
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
