import asyncio
import base64
import binascii
from dataclasses import dataclass
import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Analysis, AnalysisResult
from app.execution.models import MentorAnalysisResult
from app.services.storage import DocumentStorage


logger = logging.getLogger(__name__)

RETRYABLE_STATUSES = {408, 429, 500, 502, 503}
NON_RETRYABLE_STATUSES = {400, 401, 403, 404}
RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)


@dataclass(frozen=True)
class TtsGenerationResult:
    status: str
    audio_id: str | None
    audio_url: str | None
    format: str
    duration_ms: int
    provider: str
    source: str
    attempts: int
    latency_ms: int
    error_code: str | None = None


class TtsService:
    def __init__(self, storage: DocumentStorage | None = None) -> None:
        self.storage = storage or DocumentStorage()

    async def synthesize_analysis_summary(self, session: AsyncSession, analysis_id: str) -> TtsGenerationResult:
        analysis = await session.get(Analysis, analysis_id)
        if analysis is None:
            raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)

        audio_id = self._analysis_audio_id(analysis_id)
        path = self.storage.audio_path(audio_id)
        if self._is_valid_mp3_file(path):
            return self._result(
                status="ready",
                audio_id=audio_id,
                source="cached",
                attempts=0,
                latency_ms=0,
                duration_ms=self._estimate_duration_ms(path=path),
            )

        spoken_summary = await self._get_spoken_summary(session, analysis_id)
        if not spoken_summary:
            return self._fallback("TTS_TEXT_NOT_FOUND", attempts=0, latency_ms=0)

        return await self._generate(spoken_summary, audio_id, path)

    async def synthesize_text(self, text: str, audio_id: str | None = None) -> TtsGenerationResult:
        normalized = self._normalize_text(text)
        if not normalized:
            raise AppError("TTS_TEXT_NOT_FOUND", "Нет текста для озвучивания", status_code=422)
        resolved_audio_id = audio_id or f"tts_{uuid4()}"
        path = self.storage.audio_path(resolved_audio_id)
        if self._is_valid_mp3_file(path):
            return self._result(
                status="ready",
                audio_id=resolved_audio_id,
                source="cached",
                attempts=0,
                latency_ms=0,
                duration_ms=self._estimate_duration_ms(path=path),
            )
        return await self._generate(normalized, resolved_audio_id, path)

    async def _generate(self, text: str, audio_id: str, path: Path) -> TtsGenerationResult:
        if not settings.polza_api_key:
            return self._fallback("TTS_CONFIGURATION_MISSING", attempts=0, latency_ms=0)

        normalized = self._normalize_text(text)
        start = perf_counter()
        attempts = 0
        last_error_code = "TTS_PROVIDER_UNAVAILABLE"
        url = f"{settings.polza_base_url.rstrip('/')}/audio/speech"
        payload = {
            "model": settings.tts_model,
            "input": normalized,
            "voice": settings.tts_voice,
            "speed": settings.tts_speed,
            "response_format": "mp3",
        }
        headers = {"Authorization": f"Bearer {settings.polza_api_key}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=settings.tts_timeout_seconds) as client:
            for attempt_index in range(settings.tts_max_retries + 1):
                attempts = attempt_index + 1
                try:
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code in NON_RETRYABLE_STATUSES:
                        last_error_code = self._status_error_code(response.status_code)
                        self._log_result("fallback", attempts, start, last_error_code, source="polza")
                        return self._fallback(last_error_code, attempts=attempts, latency_ms=self._elapsed_ms(start))
                    if response.status_code in RETRYABLE_STATUSES:
                        last_error_code = self._status_error_code(response.status_code)
                        if attempt_index < settings.tts_max_retries:
                            await self._sleep_before_retry(response, attempt_index)
                            continue
                        self._log_result("fallback", attempts, start, last_error_code, source="polza")
                        return self._fallback(last_error_code, attempts=attempts, latency_ms=self._elapsed_ms(start))
                    response.raise_for_status()
                    audio = self._decode_audio_response(response)
                    path.write_bytes(audio)
                    latency_ms = self._elapsed_ms(start)
                    result = self._result(
                        status="ready",
                        audio_id=audio_id,
                        source="polza",
                        attempts=attempts,
                        latency_ms=latency_ms,
                        duration_ms=self._estimate_duration_ms(text=normalized),
                    )
                    self._log_result(result.status, attempts, start, None, source=result.source, duration_ms=result.duration_ms)
                    return result
                except RETRYABLE_EXCEPTIONS as exc:
                    last_error_code = self._exception_error_code(exc)
                    if attempt_index < settings.tts_max_retries:
                        await asyncio.sleep(2**attempt_index)
                        continue
                except httpx.HTTPStatusError as exc:
                    last_error_code = self._status_error_code(exc.response.status_code)
                    if exc.response.status_code in RETRYABLE_STATUSES and attempt_index < settings.tts_max_retries:
                        await self._sleep_before_retry(exc.response, attempt_index)
                        continue
                    break
                except Exception:
                    last_error_code = "TTS_PROVIDER_UNAVAILABLE"
                    logger.exception(
                        "tts_generation_failed model=%s voice=%s speed=%s attempts=%s status=fallback error_code=%s",
                        settings.tts_model,
                        settings.tts_voice,
                        settings.tts_speed,
                        attempts,
                        last_error_code,
                    )
                    break

        latency_ms = self._elapsed_ms(start)
        self._log_result("fallback", attempts, start, last_error_code, source="polza")
        return self._fallback(last_error_code, attempts=attempts, latency_ms=latency_ms)

    async def _get_spoken_summary(self, session: AsyncSession, analysis_id: str) -> str:
        mentor_result = (
            await session.execute(select(MentorAnalysisResult).where(MentorAnalysisResult.analysis_id == analysis_id))
        ).scalar_one_or_none()
        if mentor_result:
            text = self._extract_spoken_summary(mentor_result.result_json)
            if text:
                return text

        analysis_result = (
            await session.execute(select(AnalysisResult).where(AnalysisResult.analysis_id == analysis_id))
        ).scalar_one_or_none()
        if analysis_result:
            return self._extract_spoken_summary(analysis_result.result_json)
        return ""

    def _extract_spoken_summary(self, payload: dict) -> str:
        candidates = [
            payload.get("spoken_summary"),
            payload.get("mentor_report", {}).get("spoken_summary") if isinstance(payload.get("mentor_report"), dict) else None,
            payload.get("demo_report", {}).get("spoken_summary") if isinstance(payload.get("demo_report"), dict) else None,
            payload.get("extra_blocks", {}).get("spoken_summary") if isinstance(payload.get("extra_blocks"), dict) else None,
        ]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return self._normalize_text(candidate)
        return ""

    def _normalize_text(self, text: str) -> str:
        normalized = " ".join(text.split()).strip()
        return normalized[: settings.tts_max_text_length]

    def _decode_audio_response(self, response: httpx.Response) -> bytes:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type or response.content.lstrip().startswith(b"{"):
            payload = response.json()
            encoded = payload.get("audio") if isinstance(payload, dict) else None
            provider_content_type = payload.get("contentType") if isinstance(payload, dict) else None
            if not isinstance(encoded, str) or not encoded:
                raise ValueError("Polza TTS response does not contain audio")
            if provider_content_type and provider_content_type != "audio/mpeg":
                raise ValueError(f"Unsupported Polza TTS content type: {provider_content_type}")
            try:
                audio = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Polza TTS response contains invalid base64 audio") from exc
        else:
            audio = response.content

        if not self._is_valid_mp3(audio):
            raise ValueError("Polza TTS response is not valid MP3 data")
        return audio

    def _is_valid_mp3_file(self, path: Path) -> bool:
        if not path.exists() or path.stat().st_size < 3:
            return False
        with path.open("rb") as source:
            return self._is_valid_mp3(source.read(3))

    def _is_valid_mp3(self, audio: bytes) -> bool:
        return audio.startswith(b"ID3") or (
            len(audio) >= 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0
        )

    def _analysis_audio_id(self, analysis_id: str) -> str:
        return f"analysis_{analysis_id}"

    def _result(
        self,
        *,
        status: str,
        audio_id: str,
        source: str,
        attempts: int,
        latency_ms: int,
        duration_ms: int,
    ) -> TtsGenerationResult:
        return TtsGenerationResult(
            status=status,
            audio_id=audio_id,
            audio_url=f"/api/v1/media/audio/{audio_id}",
            format="mp3",
            duration_ms=duration_ms,
            provider="polza.ai",
            source=source,
            attempts=attempts,
            latency_ms=latency_ms,
        )

    def _fallback(self, error_code: str, *, attempts: int, latency_ms: int) -> TtsGenerationResult:
        return TtsGenerationResult(
            status="fallback",
            audio_id=None,
            audio_url=None,
            format="mp3",
            duration_ms=0,
            provider="browser",
            source="browser",
            attempts=attempts,
            latency_ms=latency_ms,
            error_code=error_code,
        )

    async def _sleep_before_retry(self, response: httpx.Response, attempt_index: int) -> None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                await asyncio.sleep(min(float(retry_after), 5))
                return
            except ValueError:
                pass
        await asyncio.sleep(2**attempt_index)

    def _status_error_code(self, status_code: int) -> str:
        return {
            400: "TTS_BAD_REQUEST",
            401: "TTS_AUTHENTICATION_FAILED",
            403: "TTS_ACCESS_DENIED",
            404: "TTS_MODEL_NOT_FOUND",
            408: "TTS_TIMEOUT",
            429: "TTS_RATE_LIMITED",
            500: "TTS_PROVIDER_UNAVAILABLE",
            502: "TTS_PROVIDER_UNAVAILABLE",
            503: "TTS_PROVIDER_UNAVAILABLE",
        }.get(status_code, "TTS_PROVIDER_UNAVAILABLE")

    def _exception_error_code(self, exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return "TTS_TIMEOUT"
        if isinstance(exc, httpx.ConnectError):
            return "TTS_CONNECTION_FAILED"
        return "TTS_PROVIDER_UNAVAILABLE"

    def _estimate_duration_ms(self, text: str | None = None, path: Path | None = None) -> int:
        if text:
            words = max(1, len(text.split()))
            return int(words / 3.0 * 1000 / max(settings.tts_speed, 0.1))
        if path and path.exists():
            return max(900, min(60000, int(path.stat().st_size / 24)))
        return 0

    def _elapsed_ms(self, start: float) -> int:
        return int((perf_counter() - start) * 1000)

    def _log_result(
        self,
        status: str,
        attempts: int,
        start: float,
        error_code: str | None,
        *,
        source: str,
        duration_ms: int = 0,
    ) -> None:
        logger.info(
            "tts_generation_completed model=%s voice=%s speed=%s latency_ms=%s attempts=%s status=%s error_code=%s audio_duration=%s source=%s",
            settings.tts_model,
            settings.tts_voice,
            settings.tts_speed,
            self._elapsed_ms(start),
            attempts,
            status,
            error_code or "",
            duration_ms,
            source,
        )
