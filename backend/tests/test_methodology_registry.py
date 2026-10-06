import io

import fitz
import pytest
from sqlalchemy import select

from app.db.models import Analysis, AnalysisResult, Document
from app.db.session import async_session_factory
from app.methodology.models import MethodologyCriterion
from app.methodology.registry import MethodologyRegistry
from app.methodology.repository import MethodologyRepository
from app.methodology.seeds.startup_vkr import ensure_startup_vkr_seed
from app.services.reports import ReportService


def make_pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Проблема, продукт, рынок и финансовая модель проекта.")
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


async def upload_pdf(client) -> dict:
    response = await client.post(
        "/api/v1/documents",
        files={"upload": ("startup.pdf", make_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_catalog_contains_all_work_types_and_only_startup_is_available(client):
    async with async_session_factory() as session:
        await ensure_startup_vkr_seed(session)

    response = await client.get("/api/v1/methodologies")
    assert response.status_code == 200, response.text
    items = response.json()
    assert len(items) == 10
    startup = next(item for item in items if item["work_type"] == "STARTUP_VKR")
    assert startup["display_name"] == "ВКР в виде стартапа"
    assert startup["availability"] == "AVAILABLE"
    assert startup["active_version"] == "2.0"
    assert startup["max_score"] == 60
    assert startup["active_methodology"]["criteria_count"] == 6
    assert all(item["availability"] == "NOT_CONFIGURED" for item in items if item["work_type"] != "STARTUP_VKR")


@pytest.mark.asyncio
async def test_registry_resolves_active_and_historical_versions():
    async with async_session_factory() as session:
        await ensure_startup_vkr_seed(session)
        registry = MethodologyRegistry(MethodologyRepository(session))
        active = await registry.resolve("STARTUP_VKR")
        historical = await registry.resolve("STARTUP_VKR", methodology_version="1.1")

    assert active.version == "2.0"
    assert active.max_score == 60
    assert historical.version == "1.1"
    assert historical.id != active.id


@pytest.mark.asyncio
async def test_unconfigured_work_type_cannot_start_analysis(client):
    document = await upload_pdf(client)
    response = await client.post(
        "/api/v1/analyses",
        json={"document_id": document["id"], "work_type": "COURSE_WORK", "mode": "demo"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "METHODOLOGY_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_analysis_persists_selected_methodology_snapshot_and_history(client):
    async with async_session_factory() as session:
        methodology = await ensure_startup_vkr_seed(session)
        criteria = (
            await session.execute(
                select(MethodologyCriterion).where(MethodologyCriterion.methodology_id == methodology.id)
            )
        ).scalars().all()
        assert len(criteria) == 6
        assert all(item.max_score == 10 for item in criteria)

    document = await upload_pdf(client)
    response = await client.post(
        "/api/v1/analyses",
        json={"document_id": document["id"], "work_type": "STARTUP_VKR", "mode": "demo"},
    )
    assert response.status_code == 200, response.text
    analysis_id = response.json()["analysis_id"]

    async with async_session_factory() as session:
        analysis = await session.get(Analysis, analysis_id)
        assert analysis.work_type == "STARTUP_VKR"
        assert analysis.methodology_id == "STARTUP_VKR"
        assert analysis.methodology_version == "2.0"
        assert analysis.methodology_name == "ВКР как стартап"
        assert analysis.methodology_max_score == 60

    history = await client.get("/api/v1/analyses/history")
    assert history.status_code == 200
    item = next(value for value in history.json()["items"] if value["analysis_id"] == analysis_id)
    assert item["work_type"] == "STARTUP_VKR"
    assert item["work_type_display_name"] == "ВКР в виде стартапа"
    assert item["methodology_name"] == "ВКР как стартап"
    assert item["methodology_version"] == "2.0"
    assert item["total_score_max"] == 60


def test_report_uses_dynamic_methodology_score_metadata():
    analysis = Analysis(
        id="analysis-dynamic-report",
        document_id="document-dynamic-report",
        analysis_type="mentor",
        work_type="EXAMPLE",
        methodology_id="EXAMPLE_METHOD",
        methodology_version="3.2",
        methodology_name="Пример методологии",
        methodology_max_score=42,
        status="completed",
        progress=100,
    )
    document = Document(
        id="document-dynamic-report",
        original_name="work.pdf",
        stored_name="stored.pdf",
        mime_type="application/pdf",
        size=1,
        checksum="x",
        storage_path="/tmp/work.pdf",
    )
    result = AnalysisResult(
        analysis_id=analysis.id,
        result_json={
            "overall_score": 21,
            "verdict": "Промежуточный результат",
            "criteria": [{"title": "Критерий", "score": 21, "max_score": 42, "explanation": "Описание"}],
        },
    )
    lines = ReportService()._build_lines(analysis, document, result.result_json)
    assert "Методология: Пример методологии 3.2" in lines
    assert "Общий балл: 21 / 42" in lines
