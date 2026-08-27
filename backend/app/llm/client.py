import asyncio
from copy import deepcopy
from email.utils import parsedate_to_datetime
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.llm.errors import LLMConfigurationError, LLMError, LLMResponseValidationError
from app.llm.registry import AGGREGATOR
from app.llm.schemas import LLMResult, LLMUsage


logger = logging.getLogger(__name__)

ERROR_CODE_BY_STATUS = {
    400: "LLM_BAD_REQUEST",
    401: "LLM_AUTHENTICATION_FAILED",
    402: "LLM_INSUFFICIENT_BALANCE",
    403: "LLM_ACCESS_DENIED",
    404: "LLM_MODEL_NOT_FOUND",
    408: "LLM_TIMEOUT",
    429: "LLM_RATE_LIMITED",
    500: "LLM_PROVIDER_UNAVAILABLE",
    502: "LLM_PROVIDER_UNAVAILABLE",
    503: "LLM_PROVIDER_UNAVAILABLE",
}
RETRYABLE_STATUSES = {408, 429, 500, 502, 503}


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int = 2,
        retry_base_delay_seconds: float = 0.5,
    ):
        self.api_key = api_key or settings.polza_api_key
        self.base_url = base_url or settings.polza_base_url
        self.timeout = timeout or settings.llm_request_timeout_seconds
        self.max_retries = max_retries
        self.retry_base_delay_seconds = retry_base_delay_seconds
        if not self.api_key:
            raise LLMConfigurationError("POLZA_API_KEY is not configured")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise LLMConfigurationError("OpenAI SDK is not installed") from exc

        # Retries are handled explicitly below so the SDK must not multiply them internally.
        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout, max_retries=0)

    async def ask(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_model: type[BaseModel],
        temperature: float = 0,
        max_completion_tokens: int | None = None,
        seed: int | None = None,
    ) -> LLMResult:
        started = time.perf_counter()
        logger.info("llm_call_started aggregator=%s requested_model=%s", AGGREGATOR, model)
        request_args: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": self._strict_json_schema(response_model),
                    "strict": True,
                },
            },
            "temperature": temperature,
        }
        if max_completion_tokens is not None:
            request_args["max_completion_tokens"] = max_completion_tokens
        if seed is not None:
            request_args["seed"] = seed

        last_error: LLMError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.chat.completions.create(**request_args)
                latency_ms = round((time.perf_counter() - started) * 1000)
                output = self._parse_response(response, response_model)
                usage = self._usage_from_response(response)
                finish_reason = self._finish_reason_from_response(response)
                provider = self._response_attr(response, "provider")
                actual_model = self._response_attr(response, "model")
                provider_response_id = self._response_attr(response, "id")
                logger.info(
                    "llm_call_completed aggregator=%s provider=%s requested_model=%s actual_model=%s "
                    "status=success latency_ms=%s total_tokens=%s cost_rub=%s finish_reason=%s",
                    AGGREGATOR,
                    provider,
                    model,
                    actual_model,
                    latency_ms,
                    usage.total_tokens,
                    usage.cost_rub,
                    finish_reason,
                )
                return LLMResult(
                    output=output,
                    provider_response_id=provider_response_id,
                    requested_model=model,
                    actual_model=actual_model,
                    aggregator=AGGREGATOR,
                    provider=provider or "unknown",
                    finish_reason=finish_reason,
                    temperature=temperature,
                    max_completion_tokens=max_completion_tokens,
                    seed=seed,
                    usage=usage,
                    latency_ms=latency_ms,
                    status="success",
                )
            except LLMError:
                logger.exception("llm_call_failed aggregator=%s requested_model=%s status=failed", AGGREGATOR, model)
                raise
            except Exception as exc:
                last_error = self._normalize_provider_error(exc)
                if attempt < self.max_retries and last_error.retryable:
                    await asyncio.sleep(self._retry_delay_seconds(exc, attempt))
                    continue
                logger.exception(
                    "llm_call_failed aggregator=%s requested_model=%s error_code=%s status=failed",
                    AGGREGATOR,
                    model,
                    last_error.code,
                )
                raise last_error from exc

        raise last_error or LLMError("LLM_PROVIDER_ERROR", "LLM provider request failed")

    def _strict_json_schema(self, response_model: type[BaseModel]) -> dict[str, Any]:
        schema = deepcopy(response_model.model_json_schema())
        self._disallow_additional_properties(schema)
        return schema

    def _disallow_additional_properties(self, schema: Any) -> None:
        if isinstance(schema, dict):
            if schema.get("type") == "object" or "properties" in schema:
                schema["additionalProperties"] = False
            for value in schema.values():
                self._disallow_additional_properties(value)
        elif isinstance(schema, list):
            for item in schema:
                self._disallow_additional_properties(item)

    def _normalize_provider_error(self, exc: Exception) -> LLMError:
        status_code = getattr(exc, "status_code", None)
        if status_code is None and exc.__class__.__name__ in {"APITimeoutError", "TimeoutException"}:
            status_code = 408
        code = ERROR_CODE_BY_STATUS.get(status_code, "LLM_PROVIDER_ERROR")
        retryable = status_code in RETRYABLE_STATUSES
        return LLMError(
            code,
            "LLM provider request failed",
            status_code=502 if status_code is None else self._api_status_code(status_code),
            details={"provider_status_code": status_code} if status_code is not None else None,
            retryable=retryable,
        )

    def _api_status_code(self, provider_status_code: int) -> int:
        if provider_status_code in {400, 401, 402, 403, 404, 408, 429}:
            return provider_status_code
        return 502

    def _retry_delay_seconds(self, exc: Exception, attempt: int) -> float:
        retry_after = self._retry_after_seconds(exc)
        if retry_after is not None:
            return retry_after
        return self.retry_base_delay_seconds * (2**attempt)

    def _retry_after_seconds(self, exc: Exception) -> float | None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if not headers:
            return None
        raw_value = headers.get("retry-after") or headers.get("Retry-After")
        if not raw_value:
            return None
        try:
            return max(float(raw_value), 0)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(raw_value)
            except (TypeError, ValueError):
                return None
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0)

    def _parse_response(self, response: Any, response_model: type[BaseModel]) -> BaseModel:
        content = response.choices[0].message.content
        if content is None:
            raise LLMResponseValidationError({"reason": "empty_content"})
        try:
            return response_model.model_validate_json(content)
        except ValidationError as exc:
            try:
                return response_model.model_validate(json.loads(content))
            except (json.JSONDecodeError, ValidationError):
                raise LLMResponseValidationError({"errors": exc.errors()}) from exc

    def _usage_from_response(self, response: Any) -> LLMUsage:
        usage = getattr(response, "usage", None)
        if usage is None:
            return LLMUsage()

        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or prompt_tokens + completion_tokens)
        prompt_details = self._usage_details(usage, "prompt_tokens_details")
        completion_details = self._usage_details(usage, "completion_tokens_details")
        cost_rub = self._extract_cost_rub(usage)
        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=int(self._detail_value(prompt_details, "cached_tokens", 0) or 0),
            reasoning_tokens=int(self._detail_value(completion_details, "reasoning_tokens", 0) or 0),
            cost_rub=cost_rub,
        )

    def _extract_cost_rub(self, usage: Any) -> Decimal | None:
        raw_cost = getattr(usage, "cost_rub", None)
        if raw_cost is None:
            raw_cost = getattr(usage, "model_extra", {}).get("cost_rub")
        if raw_cost is None:
            return None
        return Decimal(str(raw_cost))

    def _usage_details(self, usage: Any, field_name: str) -> Any:
        value = getattr(usage, field_name, None)
        if value is None:
            value = getattr(usage, "model_extra", {}).get(field_name)
        return value or {}

    def _detail_value(self, details: Any, field_name: str, default: Any = None) -> Any:
        if isinstance(details, dict):
            return details.get(field_name, default)
        return getattr(details, field_name, default)

    def _response_attr(self, response: Any, field_name: str) -> str | None:
        value = getattr(response, field_name, None)
        if value is None:
            value = getattr(response, "model_extra", {}).get(field_name)
        return str(value) if value is not None else None

    def _finish_reason_from_response(self, response: Any) -> str | None:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return None
        return self._response_attr(choices[0], "finish_reason")
