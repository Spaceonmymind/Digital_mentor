from decimal import Decimal
from types import SimpleNamespace
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from app.llm.client import LLMClient
from app.llm.errors import LLMError
from app.llm.registry import AGGREGATOR, WORKER
from app.llm.schemas import LLMTestNestedStructuredResponse


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeOpenAIClient:
    def __init__(self, outcomes):
        self.chat = SimpleNamespace(completions=FakeCompletions(outcomes))


class FakeStatusError(Exception):
    def __init__(self, status_code: int, retry_after: str | None = None):
        super().__init__("sanitized provider error")
        self.status_code = status_code
        self.response = SimpleNamespace(headers={})
        if retry_after is not None:
            self.response.headers["retry-after"] = retry_after


class NestedRisk(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"]
    score: int = Field(..., ge=0, le=10)
    note: str | None = None


class NestedSection(BaseModel):
    name: str
    risks: list[NestedRisk]


class NestedResponse(BaseModel):
    summary: str
    section: NestedSection
    items: list[NestedRisk]


def make_client(outcomes) -> LLMClient:
    client = LLMClient.__new__(LLMClient)
    client._client = FakeOpenAIClient(outcomes)
    client.max_retries = 2
    client.retry_base_delay_seconds = 0
    return client


def make_response() -> SimpleNamespace:
    return SimpleNamespace(
        id="resp-123",
        model="mistral-medium-3.5",
        provider="mistral",
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content=(
                        '{"summary":"ok","section":{"name":"finance","risks":[{"title":"margin",'
                        '"severity":"medium","score":5,"note":null}]},"items":[{"title":"market",'
                        '"severity":"low","score":2,"note":"watch"}]}'
                    )
                ),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=30,
            total_tokens=130,
            cost_rub=Decimal("0.250000"),
            prompt_tokens_details=SimpleNamespace(cached_tokens=12),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=4),
        ),
    )


@pytest.mark.asyncio
async def test_llm_client_strict_nested_schema_and_usage():
    client = make_client([make_response()])

    result = await client.ask(
        model=WORKER,
        system_prompt="Return JSON.",
        user_prompt="Describe idea.",
        response_model=NestedResponse,
        temperature=0.2,
        max_completion_tokens=200,
        seed=42,
    )

    request = client._client.chat.completions.calls[0]
    schema = request["response_format"]["json_schema"]["schema"]
    assert request["temperature"] == 0.2
    assert request["max_completion_tokens"] == 200
    assert request["seed"] == 42
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["NestedRisk"]["additionalProperties"] is False
    assert schema["$defs"]["NestedSection"]["additionalProperties"] is False
    assert schema["$defs"]["NestedRisk"]["properties"]["severity"]["enum"] == ["low", "medium", "high"]
    assert schema["$defs"]["NestedRisk"]["properties"]["score"]["minimum"] == 0
    assert schema["$defs"]["NestedRisk"]["properties"]["score"]["maximum"] == 10
    assert "anyOf" in schema["$defs"]["NestedRisk"]["properties"]["note"]

    assert result.provider_response_id == "resp-123"
    assert result.requested_model == WORKER
    assert result.actual_model == "mistral-medium-3.5"
    assert result.aggregator == AGGREGATOR
    assert result.provider == "mistral"
    assert result.finish_reason == "stop"
    assert result.usage.cached_tokens == 12
    assert result.usage.reasoning_tokens == 4
    assert result.usage.cost_rub == Decimal("0.250000")
    assert isinstance(result.output, NestedResponse)


@pytest.mark.asyncio
async def test_llm_client_retries_retryable_errors():
    client = make_client([FakeStatusError(429, retry_after="0"), make_response()])

    result = await client.ask(
        model=WORKER,
        system_prompt="Return JSON.",
        user_prompt="Describe idea.",
        response_model=LLMTestNestedStructuredResponse,
    )

    assert len(client._client.chat.completions.calls) == 2
    assert result.status == "success"


def test_llm_client_disables_sdk_level_retries():
    client = LLMClient(api_key="test-key", base_url="http://llm.test/v1", max_retries=2)
    assert client._client.max_retries == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "error_code"),
    [
        (400, "LLM_BAD_REQUEST"),
        (401, "LLM_AUTHENTICATION_FAILED"),
        (402, "LLM_INSUFFICIENT_BALANCE"),
        (403, "LLM_ACCESS_DENIED"),
        (404, "LLM_MODEL_NOT_FOUND"),
        (408, "LLM_TIMEOUT"),
        (429, "LLM_RATE_LIMITED"),
        (500, "LLM_PROVIDER_UNAVAILABLE"),
        (502, "LLM_PROVIDER_UNAVAILABLE"),
        (503, "LLM_PROVIDER_UNAVAILABLE"),
    ],
)
async def test_llm_client_normalizes_provider_errors(status_code, error_code):
    client = make_client([FakeStatusError(status_code), FakeStatusError(status_code), FakeStatusError(status_code)])

    with pytest.raises(LLMError) as exc_info:
        await client.ask(
            model=WORKER,
            system_prompt="secret system prompt",
            user_prompt="secret user prompt",
            response_model=LLMTestNestedStructuredResponse,
        )

    assert exc_info.value.code == error_code
    assert "secret" not in exc_info.value.message
    assert len(client._client.chat.completions.calls) == (3 if status_code in {408, 429, 500, 502, 503} else 1)
