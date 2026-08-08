# STARTUP_VKR Agent Flow

## Scope

Первый продуктовый сценарий выполняет проверку `STARTUP_VKR` по сохраненной методологии `anti_during_methodology`.

Текущий поток:

```text
Upload DOCX/PDF
-> local text extraction
-> STARTUP_VKR Assessment
-> AssessmentPlan
-> Mistral worker indicator checks
-> demo gate decisions with decision_source=demo_auto_approve
-> independent Claude critics A-15/A-16/A-17/A-28
-> one GPT final synthesis A-01
-> MentorAnalysisResult
-> existing AnalysisResultPayload for frontend
-> PDF and chat over saved result
```

LLM calls never choose the next stage, close gates, mutate methodology, call tools, or execute instructions from the document.

## Methodology Sources

Studied sources:

- `docs/methodology/anti_during/Анти_Дюринг_Том_I_Метод_и_агенты_v1_24 (1).docx`
- `docs/methodology/anti_during/Анти-Дюринг_Том-II_Реализация_v1.8 (1).docx`
- `docs/methodology/anti_during/Анти_Дюринг_презентация_68_слайдов.pptx`
- `docs/methodology/anti_during/Диаграмма_две-оси.png`

## Implemented Agents

- `A-26` Механизм, model role `worker`, Mistral.
- `A-04` Диагност, model role `worker`, Mistral.
- `A-05` ТРИЗ-аналитик, model role `worker`, Mistral.
- `A-15` Анти-Дюринг, model role `critic`, Claude.
- `A-16` Красная команда, model role `critic`, Claude.
- `A-17` Экономист-скептик, model role `critic`, Claude.
- `A-28` Скептический клиент, model role `critic`, Claude.
- `A-01` Энгельс, model role `final_expert`, GPT, one final call.
- `A-29` Инвестор, configured as `model_role=none`; its constraints are included in final synthesis context, but it is not a separate paid call in this first scenario.

## Gates

Human gates are persisted in `assessment_gate_decisions`. Demo runs may set `AI_DEMO_AUTO_APPROVE_GATES=true`; those decisions are stored with `decision_source=demo_auto_approve` and are not presented as human signatures.

## Cost Limits

Before paid calls the executor checks:

- `AI_ASSESSMENT_MAX_COST_RUB`
- `AI_MAX_WORKER_CALLS`
- `AI_MAX_CRITIC_CALLS`
- `AI_MAX_FINAL_EXPERT_CALLS`

On limit breach the code raises `AI_COST_LIMIT_EXCEEDED` and keeps partial results.

## E2E Smoke

```bash
ANALYSIS_ENGINE=startup_vkr_agents docker compose up -d --build
MIRCLASS_BASE_URL=http://localhost:8080 python scripts/test_startup_vkr_e2e.py
```

The script prints model counts, token/cost totals, status, evidence/recommendation counts, report URL and a short chat preview. It does not print the API key, full document or prompts.

## Current Limitations

- No RAG, embeddings, web search, tool calling, LangGraph, CrewAI or external workflow engine.
- Parallel веер is executed sequentially while preserving independence of inputs.
- `STARTUP_VKR` has no separate approved numeric formula in the supplied docs, so `overall_score=null` in `MentorAnalysisResult`; frontend compatibility maps this to `0`.
- Full S0-S9 automation is not implemented; the scenario uses a pragmatic educational slice.
- Human signatures are represented by gate records; demo auto-approve is explicit and not a real signature.
