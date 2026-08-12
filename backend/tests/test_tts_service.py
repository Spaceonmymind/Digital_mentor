import base64

import httpx
import pytest
from uuid import uuid4

from app.db.models import Analysis, AnalysisResult, Document
from app.db.session import async_session_factory
from app.core.config import settings
from app.services.storage import DocumentStorage
from app.services.tts_service import TtsService
from app.schemas.tts import TtsRequest


async def _create_completed_analysis(session, spoken_summary: str = "Короткое голосовое резюме.") -> Analysis:
    document_id = str(uuid4())
    analysis_id = str(uuid4())
    document = Document(
        id=document_id,
        original_name="work.docx",
        stored_name="work.docx",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size=10,
        checksum="abc",
        storage_path="/tmp/work.docx",
        extraction_status="completed",
        status="uploaded",
    )
    analysis = Analysis(
        id=analysis_id,
        document_id=document_id,
        methodology_id="STARTUP_VKR",
        methodology_version="1.1",
        status="completed",
        progress=100,
        current_step="completed",
    )
    result = AnalysisResult(
        analysis_id=analysis_id,
        result_json={"mentor_report": {"spoken_summary": spoken_summary}},
    )
    session.add_all([document, analysis, result])
    await session.commit()
    return analysis


@pytest.mark.asyncio
async def test_tts_returns_cached_analysis_audio_without_provider():
    async with async_session_factory() as session:
        analysis = await _create_completed_analysis(session)
        audio_id = f"analysis_{analysis.id}"
        path = DocumentStorage().audio_path(audio_id)
        path.write_bytes(b"ID3cached")

        result = await TtsService().synthesize_analysis_summary(session, analysis.id)

        assert result.status == "ready"
        assert result.source == "cached"
        assert result.audio_id == audio_id
        assert result.audio_url == f"/api/v1/media/audio/{audio_id}"
        assert result.attempts == 0


@pytest.mark.asyncio
async def test_tts_fallback_does_not_change_completed_analysis_status():
    original_key = settings.polza_api_key
    object.__setattr__(settings, "polza_api_key", None)
    try:
        async with async_session_factory() as session:
            analysis = await _create_completed_analysis(session)

            result = await TtsService().synthesize_analysis_summary(session, analysis.id)
            await session.refresh(analysis)

            assert result.status == "fallback"
            assert result.source == "browser"
            assert result.error_code == "TTS_CONFIGURATION_MISSING"
            assert analysis.status == "completed"
    finally:
        object.__setattr__(settings, "polza_api_key", original_key)


def test_tts_decodes_polza_json_audio_response():
    mp3 = b"ID3remote-audio"
    response = httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={
            "audio": base64.b64encode(mp3).decode("ascii"),
            "contentType": "audio/mpeg",
            "model": "gpt-4o-mini-tts",
            "usage": {},
        },
    )

    assert TtsService()._decode_audio_response(response) == mp3


def test_tts_accepts_binary_mp3_response():
    mp3 = b"ID3binary-audio"
    response = httpx.Response(200, headers={"content-type": "audio/mpeg"}, content=mp3)

    assert TtsService()._decode_audio_response(response) == mp3


def test_tts_rejects_json_saved_as_mp3(tmp_path):
    path = tmp_path / "broken.mp3"
    path.write_text('{"audio":"not-an-mp3"}')

    assert TtsService()._is_valid_mp3_file(path) is False


def test_tts_dialog_request_accepts_long_mentor_answer():
    text = "Длинный ответ ментора. " * 70

    request = TtsRequest(text=text)

    assert len(request.text) > 700
    assert TtsService()._normalize_text(request.text, settings.tts_dialog_max_text_length) == request.text.strip()
