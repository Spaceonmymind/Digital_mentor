import asyncio
import io

import fitz
import pytest
from docx import Document as DocxDocument
from sqlalchemy import select

from app.api.v1 import documents as documents_api
from app.db.models import AnalysisEvent
from app.db.session import async_session_factory


def make_pdf_bytes(text: str = "Методы исследования\nДля анализа был использован сравнительный подход.") -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def make_docx_bytes(text: str = "Методы исследования") -> bytes:
    document = DocxDocument()
    document.add_heading(text, level=2)
    document.add_paragraph("Для анализа был использован сравнительный подход.")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def upload_pdf(client):
    response = await client.post(
        "/api/v1/documents",
        files={"upload": ("work.pdf", make_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def wait_for_completed_analysis(client, analysis_id: str):
    for _ in range(50):
        status_response = await client.get(f"/api/v1/analyses/{analysis_id}")
        assert status_response.status_code == 200, status_response.text
        payload = status_response.json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        await asyncio.sleep(0.05)
    raise AssertionError("analysis did not finish in time")


@pytest.mark.asyncio
async def test_healthcheck(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_upload_pdf_success(client):
    payload = await upload_pdf(client)
    assert payload["name"] == "work.pdf"
    assert payload["mime_type"] == "application/pdf"
    assert payload["size"] > 0
    assert payload["status"] == "uploaded"


@pytest.mark.asyncio
async def test_upload_docx_success(client):
    response = await client.post(
        "/api/v1/documents",
        files={
            "upload": (
                "work.docx",
                make_docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["name"] == "work.docx"
    assert payload["status"] == "uploaded"


@pytest.mark.asyncio
async def test_reject_wrong_format(client):
    response = await client.post(
        "/api/v1/documents",
        files={"upload": ("work.txt", b"plain text", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_reject_file_over_size_limit(client):
    original_limit = documents_api.settings.max_upload_size_mb
    object.__setattr__(documents_api.settings, "max_upload_size_mb", 0)
    try:
        response = await client.post(
            "/api/v1/documents",
            files={"upload": ("work.pdf", make_pdf_bytes(), "application/pdf")},
        )
    finally:
        object.__setattr__(documents_api.settings, "max_upload_size_mb", original_limit)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_create_analysis_progress_and_result(client):
    document = await upload_pdf(client)
    create_response = await client.post(
        "/api/v1/analyses",
        json={
            "document_id": document["id"],
            "analysis_type": "mentor",
            "methodology_id": "mentor-default",
            "methodology_version": "draft",
        },
    )
    assert create_response.status_code == 200, create_response.text
    analysis_id = create_response.json()["analysis_id"]

    status = await wait_for_completed_analysis(client, analysis_id)
    assert status["status"] == "completed"
    assert status["progress"] == 100

    result_response = await client.get(f"/api/v1/analyses/{analysis_id}/result")
    assert result_response.status_code == 200, result_response.text
    result = result_response.json()
    assert result["analysis_id"] == analysis_id
    assert result["overall_score"] == 87
    assert result["criteria"]

    async with async_session_factory() as session:
        events = (
            await session.execute(select(AnalysisEvent).where(AnalysisEvent.analysis_id == analysis_id))
        ).scalars().all()
    assert len(events) >= 9
    assert max(event.progress for event in events) == 100


@pytest.mark.asyncio
async def test_create_analysis_missing_document(client):
    response = await client.post(
        "/api/v1/analyses",
        json={
            "document_id": "missing",
            "analysis_type": "mentor",
            "methodology_id": "mentor-default",
            "methodology_version": "draft",
        },
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_chat_without_analysis_id_is_rejected(client):
    response = await client.post("/api/v1/chat/messages", json={"message": "Почему снижена оценка?"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_response_for_analysis(client):
    document = await upload_pdf(client)
    create_response = await client.post(
        "/api/v1/analyses",
        json={
            "document_id": document["id"],
            "analysis_type": "mentor",
            "methodology_id": "mentor-default",
            "methodology_version": "draft",
        },
    )
    analysis_id = create_response.json()["analysis_id"]
    await wait_for_completed_analysis(client, analysis_id)

    response = await client.post(
        "/api/v1/chat/messages",
        json={"analysis_id": analysis_id, "message": "Как получить больше 90 баллов?"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["message_id"]
    assert "90" in payload["answer"]
