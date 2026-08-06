import logging
import time
from collections.abc import Callable

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_session
from app.llm.client import LLMClient
from app.llm.errors import LLMError
from app.llm.registry import AGGREGATOR, WORKER
from app.llm.schemas import LLMCallTraceCreate, LLMTestRequest, LLMTestResponse, LLMTestStructuredResponse
from app.llm.trace_service import LLMTraceService


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/internal/llm", tags=["internal-llm"])


def get_llm_client() -> Callable[[], LLMClient]:
    return LLMClient


@router.post("/test", response_model=LLMTestResponse)
async def test_llm(
    payload: LLMTestRequest,
    session: AsyncSession = Depends(get_session),
    llm_client_factory: Callable[[], LLMClient] = Depends(get_llm_client),
) -> LLMTestResponse:
    trace_service = LLMTraceService(session)
    started = time.perf_counter()
    try:
        llm_client = llm_client_factory()
        result = await llm_client.ask(
            model=WORKER,
            system_prompt=payload.system_prompt,
            user_prompt=f"Описание идеи:\n{payload.text}",
            response_model=LLMTestStructuredResponse,
        )
    except LLMError:
        await trace_service.record(
            LLMCallTraceCreate(
                requested_model=WORKER,
                aggregator=AGGREGATOR,
                latency_ms=round((time.perf_counter() - started) * 1000),
                status="failed",
            )
        )
        raise
    except Exception as exc:
        await trace_service.record(
            LLMCallTraceCreate(
                requested_model=WORKER,
                aggregator=AGGREGATOR,
                latency_ms=round((time.perf_counter() - started) * 1000),
                status="failed",
            )
        )
        logger.exception("llm_test_failed")
        raise AppError("LLM_TEST_FAILED", "Не удалось выполнить тестовый LLM-запрос", status_code=502) from exc

    await trace_service.record_result(result)
    output = result.output
    return LLMTestResponse(
        summary=output.summary,
        keywords=output.keywords,
        tokens=result.usage.total_tokens,
        cost_rub=result.usage.cost_rub,
        provider=result.provider,
        requested_model=result.requested_model,
        actual_model=result.actual_model,
        provider_response_id=result.provider_response_id,
        latency_ms=result.latency_ms,
    )
