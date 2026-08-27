# Digital Mentor — Master Context

Актуально по состоянию репозитория на 2026-08-12. Источник истины: фактический код в репозитории. Если этот файл расходится с кодом, доверять коду и обновить этот файл после изменений.

## 1. Назначение проекта

Digital Mentor, или "Цифровой ментор", — приложение для анализа учебных и проектных работ, в первую очередь сценария "ВКР как стартап". Пользователь загружает PDF/DOCX, backend локально извлекает текст, запускает AI-анализ по методологии, сохраняет результат, показывает короткий понятный разбор во frontend, позволяет скачать PDF, прослушать краткое голосовое резюме и продолжить диалог в чате.

Фактический основной пользовательский flow:

```text
Пользователь
  -> frontend upload
  -> POST /api/v1/documents
  -> локальное сохранение файла и content.json
  -> POST /api/v1/analyses
  -> background analysis task
  -> выбранный AnalysisEngine
  -> methodology / assessment / agents
  -> Polza.ai LLM calls
  -> AnalysisResult + MentorAnalysisResult
  -> frontend result / detailed PDF / chat / optional TTS
```

Для демонстраций сейчас ключевой режим — быстрый, но все еще мультиагентный `demo` flow для `STARTUP_VKR`.

## 2. Текущий статус

IMPLEMENTED:

- Static frontend на vanilla HTML/CSS/JavaScript под nginx.
- FastAPI backend с PostgreSQL, SQLAlchemy async и Alembic.
- Upload PDF/DOCX, проверка расширения/MIME/signature/размера, локальное хранение.
- Извлечение текста PDF через PyMuPDF и DOCX через python-docx в `content.json`.
- Health endpoints, request id, единый формат ошибок.
- `documents`, `analyses`, events/progress, cancel, result endpoints.
- `UNIVERSAL_DOCUMENT` worker execution.
- Активная `STARTUP_VKR` версии `2.0` по регламенту ВКР-стартапа Финансового университета; версия `1.1` Anti-Duhring сохранена для старых результатов.
- Методологические сущности: methodology, criteria, indicators, prompt templates, methodology agents.
- Assessment pipeline, plan builder, task runs, agent task runs, gates, agent results.
- Polza.ai через OpenAI-compatible `LLMClient`.
- Model registry: Mistral worker, Claude critic, GPT final expert.
- Strict JSON Schema structured output и трассировка `llm_calls`.
- Full/standard STARTUP_VKR flow: worker indicators -> critic agents -> A-01 final report.
- Demo STARTUP_VKR flow: A-15/A-16/A-17/A-28 parallel -> A-01 final.
- Demo scoring 0-10 per criterion и overall 0-60.
- `MentorReport` и `TechnicalAssessmentResult` schemas.
- User-facing result normalization во frontend.
- PDF report и async detailed report.
- Chat по сохраненному результату и релевантным фрагментам документа.
- Optional remote TTS через Polza.ai plus browser fallback.
- Browser STT via SpeechRecognition.
- Frontend mascot/image state handling.
- Backend pytest suites and frontend smoke test.

PARTIALLY IMPLEMENTED:

- File security scan is stub (`StubFileSecurityService`), not real antivirus.
- OCR отсутствует; PDF без текстового слоя не распознается.
- Detailed PDF is assembled from saved analysis and extracted text fragments; it is not a separate deep LLM report yet.
- Full `STARTUP_VKR` standard flow exists but demo mode is the practical fast UI scenario.
- Human gates exist as endpoints and `GateDecision`, but demo auto-approve is commonly used.
- TTS remote service exists, but browser fallback is expected and must stay non-blocking.
- STT is browser-only, no server-side speech-to-text.
- Frontend local history is browser-local, not server account history.

PLANNED / NOT IMPLEMENTED:

- Production authentication, users, roles, multi-tenant workspace.
- Real antivirus/FSS provider.
- OCR for scanned PDFs.
- RAG, embeddings, vector database.
- Web search/tool calling.
- Full production state machine for all S0-S9 transitions.
- Production human signature workflow.
- 3D/Live2D avatar.
- Server-side STT.
- Separate deep LLM-generated detailed report with diagrams.

## 3. Архитектура

High-level components:

- Frontend: nginx-served static UI, vanilla JS modules, CSS, assets.
- Backend API: FastAPI app, routers under `backend/app/api/v1`.
- DB: PostgreSQL in Docker; SQLite in tests.
- Storage: local filesystem under `storage/`.
- AI layer: Polza.ai through `LLMClient` and model registry.
- Assessment/methodology: SQLAlchemy entities plus seed/import logic.
- Execution: worker executor, STARTUP_VKR orchestration, demo/full flows.
- Reports: immediate result JSON, user PDF, async detailed PDF.
- Chat: saved result + relevant document fragments + Claude role.
- TTS: independent optional layer over `spoken_summary`.

Actual flow:

```text
Browser
  |
  v
frontend nginx static UI
  |
  v
FastAPI /api/v1
  |
  +-- Document upload -> DocumentStorage -> TextExtractionService -> content.json
  |
  +-- Analysis create -> BackgroundTasks -> run_analysis_task
                                  |
                                  v
                           get_analysis_engine()
                                  |
              +-------------------+--------------------+
              |                   |                    |
              v                   v                    v
        MockAnalysisEngine  AssessmentWorkerEngine  StartupVkrAnalysisEngine
                                                   |
                       +---------------------------+-------------------------+
                       |                                                     |
                       v                                                     v
             standard/expert-style flow                              demo flow
             workers -> critics -> A-01                  A-15/A-16/A-17/A-28 in gather -> A-01
                       |                                                     |
                       v                                                     v
                    Polza.ai LLMClient + llm_calls trace
                       |
                       v
         AnalysisResult / MentorAnalysisResult / AgentResult / task runs
                       |
                       v
          frontend result / PDF / detailed report / chat / optional TTS
```

## 4. Структура репозитория

Important tree:

```text
backend/
  Dockerfile
  start.sh                         # Alembic upgrade then uvicorn
  requirements.txt
  alembic/versions/                # DB migrations 0001-0010
  app/
    main.py                        # FastAPI app and routers
    api/v1/                        # public/internal API routers
    assessment/                    # Assessment domain models/repository
    core/                          # config, errors, middleware
    db/                            # SQLAlchemy base/session/models
    execution/                     # context, schemas, worker, startup_vkr orchestration
    llm/                           # Polza.ai client, registry, trace service
    methodology/                   # methodology models, repo, seeds
    pipeline/                      # artifact/methodology resolver and plan builder
    schemas/                       # public DTOs
    services/                      # storage, extraction, reports, chat, TTS
    workers/                       # background analysis task
  tests/                           # pytest suites

frontend/
  Dockerfile
  nginx.conf                       # static frontend + /api proxy
  index.html
  src/js/                          # app.js, api.js, modules
  src/styles/                      # global styles and variables
  src/assets/                      # fonts, logos, mascot images
  tests/smoke.mjs

docs/
  methodology/anti_during/         # source methodology docs
  startup_vkr_agent_flow.md

demo/
  sample-document.pdf
  sample-document.docx

scripts/
  test_assessment_worker.py
  test_startup_vkr_e2e.py
  start.sh / stop.sh / test.sh / backup.sh / restore.sh / reset-demo.sh

storage/
  documents/
  extracted/
  reports/
  audio/                           # created lazily by TTS service

docker-compose.yml
.env.example
Makefile
README.md                          # currently partly stale; code is source of truth
```

## 5. Backend

Entrypoint:

- `backend/app/main.py` creates FastAPI app.
- `backend/start.sh` runs `alembic upgrade head` with retry, then starts `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

Configuration:

- `backend/app/core/config.py` reads env into immutable `Settings`.
- Important toggles: `ANALYSIS_ENGINE`, `DEMO_MODE`, `FRONTEND_MOCK_MODE`, `TTS_MODE`, `POLZA_API_KEY`, AI token/cost limits.

Routers:

- Public: health, documents, analyses, assessments, chat, tts, media, config.
- Internal: assessment creation/execution, gates/resume/retry, LLM test, methodology import/list, pipeline build.

DB:

- SQLAlchemy async with PostgreSQL in Docker.
- Tests override DB to in-memory SQLite.

Error handling:

- `AppError` and request id middleware produce structured errors.
- Startup marks queued/processing analyses as failed with `PROCESS_INTERRUPTED`.

Background execution:

- `POST /api/v1/analyses` creates `Analysis` with status `queued`.
- FastAPI `BackgroundTasks` calls `run_analysis_task`.
- `run_analysis_task` selects engine via `get_analysis_engine()`.

## 6. Frontend

Technology:

- Static HTML/CSS/JS; no npm build pipeline for production assets.
- `frontend/Dockerfile` copies `index.html`, `src`, and `demo` into nginx.

Structure:

- `frontend/src/js/app.js`: main UI state, screens, result rendering, speech, detailed report, chat.
- `frontend/src/js/api.js`: API client.
- `frontend/src/js/modules/analysis.js`: creates analysis and polls status.
- `frontend/src/js/modules/speech.js`: remote TTS wrapper, browser TTS fallback, browser STT.
- `frontend/src/js/modules/mascot.js`: mascot state/image fallback.
- `frontend/src/js/modules/history.js`: browser-local history.
- `frontend/src/styles/global.css`: full UI styling.

Upload flow:

- User selects/drag-drops PDF/DOCX.
- `uploadDocument()` calls `POST /api/v1/documents`.
- Start analysis button calls `runAnalysis(documentId)`.

Analysis progress:

- Frontend polls `GET /api/v1/analyses/{analysis_id}` every 1400 ms.
- If `/api/v1/config` returns `demo_mode=true`, frontend sends `mode: "demo"`.
- Processing UI maps backend progress/current_step to user labels: preparation, parallel checks, final synthesis, completed.

Result rendering:

- Frontend normalizes legacy results, demo report, and mentor report.
- Demo report shows overall score out of 60, six criteria, strengths, objections/remarks, recommendations.
- Mentor report shows current stage and P1.12-style content if present.

Report:

- Detailed report starts after quick result with `POST /api/v1/analyses/{id}/detailed-report`.
- Download button uses detailed report URL once ready.

Chat:

- `POST /api/v1/chat/messages`.
- Fallback mock answer if backend call fails.

Speech/TTS:

- Configured by `/api/v1/config.tts_mode`.
- `remote` uses `RemoteTtsSpeechService`.
- For remote mode, server TTS is only used when `analysisId` is supplied; intermediate UI status phrases do not call remote TTS.
- Browser SpeechSynthesis is fallback.

## 7. Document Pipeline

Exact chain:

```text
POST /api/v1/documents
  -> _validate_upload
  -> DocumentStorage.save
  -> StubFileSecurityService.scan
  -> Document row
  -> TextExtractionService.extract
  -> storage/extracted/{document_id}/content.json
  -> document.extraction_status = completed
```

Supported formats:

- `.pdf` with MIME `application/pdf` and `%PDF` header.
- `.docx` with MIME `application/vnd.openxmlformats-officedocument.wordprocessingml.document` and ZIP structure.

Limits:

- `MAX_UPLOAD_SIZE_MB`, default 50.
- Allowed types from `ALLOWED_FILE_TYPES`.

Security:

- File security service is currently a stub returning `not_performed`.
- Filenames are normalized via `PurePath(...).name`.
- Stored filenames are UUID-based.
- Path reads/writes resolve under storage dirs.

Extraction:

- PDF: PyMuPDF pages, blocks, bbox, full_text.
- DOCX: python-docx paragraphs, styles, full_text.
- OCR: NOT IMPLEMENTED.
- Scanned PDFs without text layer fail with `DOCUMENT_TEXT_NOT_FOUND`.

Assessment:

- Analysis requires `document.extraction_status == completed`.
- Startup analysis builds an assessment through `PipelineService`.

## 8. Методологии

Supported artifact types in `ArtifactResolver`:

- `UNIVERSAL_DOCUMENT`
- `STARTUP_VKR`

Resolution:

- Explicit `artifact_type` is normalized and validated.
- If not provided, filename/metadata containing `startup`, `вкр`, or `стартап` maps to `STARTUP_VKR`; otherwise `UNIVERSAL_DOCUMENT`.
- `MethodologyResolver` returns active methodology by code via repository.

Versioning:

- `Methodology` is unique by `(code, version)`.
- Active/latest selection is repository-driven.
- Old versions are kept for reproducibility.

Entities:

- `Methodology`
- `MethodologyCriterion`
- `MethodologyIndicator`
- `PromptTemplate`
- `MethodologyAgent`

Current active startup methodology:

- `STARTUP_VKR` version `2.0`.
- `source = FinUniversity VKR Startup Regulation, Order №3136/o dated 20.12.2023`.
- `is_demo = false`.
- Six criteria C1-C6 cover problem/relevance, innovation/product, market/audience, business model, financial feasibility, and risks/development.
- Regulation requirements are represented as internal indicators; weights remain nullable.
- Versions `1.0` and `1.1` remain stored and readable but inactive for new assessments.

Universal document:

- Exists for first worker execution and mock/technical assessment worker mode.
- It is not the production STARTUP_VKR methodology.

## 9. Методология Anti-Dühring

Source docs present:

- `docs/methodology/anti_during/АнтиДюринг_ТомI_ред1.26.docx`
- `docs/methodology/anti_during/АнтиДюринг_ТомII_ред1.10.docx`
- Previous docs and presentation are also present in same directory.

Implementation references:

- Method version: `1.26`.
- Implementation version: `1.10`.
- P1.12 user report structure is represented by `MentorReport`.
- Seed/import path: `backend/app/methodology/seeds/startup_vkr/`.

Link:

```text
Anti-Dühring docs
  -> startup_vkr seed data
  -> Methodology / criteria / indicators / prompt templates / agents
  -> Assessment / AgentTaskRun
  -> Worker/Critic/A-01 outputs
  -> MentorReport and TechnicalAssessmentResult
```

Important implementation rules:

- A-01 is the single external user-facing voice.
- Raw Worker/Critic/GPT traces are internal/technical data.
- LLM must not choose next stage, pass gates, mutate methodology, or execute document instructions.
- A-15 contains 9 checks, including "заявленное свойство противоречит устройству".

## 10. Мультиагентная архитектура

Implemented agents in STARTUP_VKR seeds:

| Agent | Role | Model role | Execution mode | Current use |
| --- | --- | --- | --- | --- |
| A-26 | Механизм | worker | sequential | Standard/full worker plan |
| A-04 | Диагност | worker | sequential | Standard/full worker plan |
| A-05 | ТРИЗ-аналитик | worker | sequential | Standard/full worker plan |
| A-15 | Проблема и актуальность | critic in DB, Mistral in demo config | parallel | C1 and customer-need part of C3 |
| A-16 | Бизнес-модель и финансы | critic / Claude | parallel | C4, C5 and commercialization |
| A-17 | Инновационность и продукт | critic in DB, Mistral in demo config | parallel | C2 and feasibility part of C6 |
| A-28 | Рынок, риски и развитие | critic / Claude | parallel | C3, C6 and strategic challenge |
| A-01 | Энгельс / final external synthesis | final_expert / GPT | final | Demo and standard final |
| A-29 | Инвестор | none | final | Configured in DB but not currently LLM-executed |

Demo mode actual model mapping in code:

- A-15 -> `mistralai/mistral-medium-3-5`
- A-16 -> `anthropic/claude-sonnet-5`
- A-17 -> `mistralai/mistral-medium-3-5`
- A-28 -> `anthropic/claude-sonnet-5`
- A-01 -> `openai/gpt-5.6-sol-pro`

Demo execution:

- A-15/A-16/A-17/A-28 are launched with `asyncio.gather(..., return_exceptions=True)`.
- A-01 starts only after all demo agent results are available.

Standard/full execution:

- Worker indicator tasks run through `AssessmentPlanExecutor` and `WorkerExecutor`.
- Critic agents run in a loop in current code, so standard critic execution is sequential.
- A-01 final runs once after critics.

## 11. LLM Provider

Provider aggregator:

- Polza.ai.
- Base URL env: `POLZA_BASE_URL`, default code value is `https://polza.ai/api/v1`.
- API key env: `POLZA_API_KEY` (never hardcode or commit actual value).
- API style: OpenAI-compatible Chat Completions.

`LLMClient`:

- Uses `openai.AsyncOpenAI`.
- Sends `messages`, `model`, `temperature`, `max_completion_tokens`, optional `seed`.
- Uses `response_format={"type": "json_schema", "json_schema": {"strict": true, ...}}`.
- Converts Pydantic schemas to strict JSON schemas with recursive `additionalProperties=false`.

Retries/timeouts:

- `LLM_REQUEST_TIMEOUT_SECONDS`, default 60.
- Retries for retryable provider statuses such as 408, 429, 500, 502, 503.
- Auth/config/model errors are not retried.

Trace:

- `LLMTraceService` writes `llm_calls`.
- Captured: requested_model, actual_model, provider_response_id, aggregator, provider, finish_reason, temperature, max_completion_tokens, seed, linked IDs, prompt/completion/total/cached/reasoning tokens, cost_rub, latency_ms, status, created_at.
- Full prompts and API keys are not persisted by this trace table.

## 12. Реестр моделей

Actual constants in `backend/app/llm/registry.py`:

- `WORKER = "mistralai/mistral-medium-3-5"`
- `CRITIC = "anthropic/claude-sonnet-5"`
- `FINAL_EXPERT = "openai/gpt-5.6-sol-pro"`
- `AGGREGATOR = "polza.ai"`

Roles:

- Worker/Mistral: primary indicator/task analysis and some demo agents.
- Critic/Claude: criticism, chat model, some demo agents.
- Final Expert/GPT: A-01 final synthesis; should not be used for every indicator or every chat message.

## 13. Demo Mode

Goal:

- Fast presentation flow, target around 30-60 seconds.
- Must stay multi-agent; do not collapse to one generic LLM.

How enabled:

- Backend public config: `DEMO_MODE=true`.
- Frontend reads `GET /api/v1/config`.
- `frontend/src/js/modules/analysis.js` sends `mode: "demo"` when `window.__MENTOR_DEMO_MODE__` is true.
- Backend `Analysis.mode` supports `demo`, `standard`, `expert`.
- `StartupVkrAnalysisEngine.run(..., mode="demo")` calls `_run_demo`.

Actual demo agents:

```text
A-15 -> problem/relevance/customer need -> Mistral
A-16 -> business model/finance/commercialization -> Claude
A-17 -> product/innovation/MVP/feasibility -> Mistral
A-28 -> market/competitors/risks/development -> Claude
A-01 -> compact results of previous agents -> GPT
```

Context:

- `_document_blocks` uses `DocumentExcerptBuilder(max_chars=24000)`.
- Keyword extraction builds focused blocks for problem, audience/market, product, technology/MVP, business model, finance, competitors, risks/development, results and conclusion.
- Each block is limited to about 5000 chars.
- Demo agents get only configured blocks, not the entire extracted text.

Parallelism:

- A-15/A-16/A-17/A-28 are launched through `asyncio.gather`.
- A-01 waits for the barrier.

Token limits in current code:

- Demo agents: `max_completion_tokens=1200` for the two-criterion structured output.
- Demo final A-01: `max_completion_tokens=1800` for the six-criterion report.

Fallback:

- If `DemoFinalReport` generation fails, code builds a deterministic fallback final report from agent outputs.
- Agent-level demo failures still fail the demo flow.

Output:

- `AnalysisResultPayload.extra_blocks.demo_report`.
- Short user-facing C1-C6 score result with collapsed per-criterion strengths/issues.
- `spoken_summary` targets roughly 20-35 seconds.
- Disclaimer states that the analytical score does not replace the decision of the State Examination Commission.
- Trace entries are present but UI should avoid exposing technical agent codes to ordinary users.

## 14. Scoring

Demo scoring for STARTUP_VKR 2.0:

- Six criteria: `C1 Проблема и актуальность`, `C2 Инновационность и продукт`, `C3 Рынок и целевая аудитория`, `C4 Бизнес-модель`, `C5 Финансовая реализуемость`, `C6 Риски и развитие`.
- Each criterion is 0-10.
- Overall score is 0-60.
- Specialized agents return compact criterion assessments with score recommendation, strengths, issues, evidence and confidence.
- Quotes not found verbatim in the supplied block become `null` instead of synthetic user evidence.
- `DemoFinalReport` requires ordered C1-C6 and normalizes overall score to the sum of criteria.

The result is a preliminary Digital Mentor assessment, not an official university grade. Pitch quality is excluded because the system analyzes the document rather than the defense speech.

Standard/P1.12 scoring:

- `MentorReport.stage_assessments` use 0-5 scale.
- No 100-point overall score should be invented for P1.12 mentor report.

Legacy result schema:

- `AnalysisResultPayload.overall_score` is still an integer for frontend compatibility.
- Demo uses 0-60.
- Older/mock flows may still use 0-100.

## 15. MentorReport

There are two conceptual DTOs:

- `MentorReport`: user-facing A-01 report.
- `TechnicalAssessmentResult`: internal agent/trace package.

`MentorReport` structure:

- `header`
- `what_this_work_is`
- `veto`
- `what_survived`
- `objections`
- `one_question`
- `one_next_step`
- `stage_assessments`
- `mentor_block`
- `spoken_summary`

Validation:

- Blocks must be present.
- Objections are limited to key items.
- Exactly one question and one next step are modeled.
- Stage scores are 0-5 and need `next_level_requirement`.
- User-facing text must not contain internal terms such as raw Worker/Critic labels, LLMCall, UUIDs, providers, tokens, costs, `quote_not_found...`.

Visibility:

- `mentor_block` is hidden from student result unless `MENTOR_BLOCK_VISIBLE_TO_STUDENT=true`.
- Technical result remains available through internal API.

Demo report:

- Demo flow uses separate `DemoFinalReport` in `extra_blocks.demo_report`.
- It is shorter and score-oriented for university/demo presentation.

## 16. PDF Report

Service:

- `backend/app/services/reports.py` (`ReportService`).
- Renders PDFs with PyMuPDF and local Golos fonts.
- Saves under `storage/reports/{analysis_id}/{report_id}.pdf`.

Endpoints:

- `POST /api/v1/analyses/{analysis_id}/reports`
- `GET /api/v1/analyses/{analysis_id}/reports/{report_id}`
- `POST /api/v1/analyses/{analysis_id}/detailed-report`
- `GET /api/v1/analyses/{analysis_id}/detailed-report/status`
- `GET /api/v1/analyses/{analysis_id}/detailed-report/download`

User PDF:

- If `mentor_report` exists, uses P1.12-style report lines.
- If `demo_report` exists, uses short demo report: overall score, criteria, strengths, remarks, recommendations, conclusion.

Detailed PDF:

- Async `DetailedReport` row tracks status/progress.
- Built from saved analysis result and locally extracted document fragments.
- Does not block quick result.
- Does not run a second LLM call in current code.

Student-facing PDFs should not include system prompts, API keys, provider IDs, raw `llm_calls`, tokens, or costs.

## 17. Chat

Endpoint:

- `POST /api/v1/chat/messages`

Storage:

- `ChatMessage` rows store user/assistant messages linked to `analysis_id`.

Model:

- Uses `CRITIC`, currently Claude Sonnet 5 through Polza.ai.
- GPT final expert is not used for every chat message.

Context:

- For completed `STARTUP_VKR` analyses, chat sends compact saved result plus relevant source document fragments.
- Relevant fragments come from `document_context.relevant_document_fragments`.
- Chat prompt says A-01 is the external voice and forbids internal agent/model/provider/cost/UUID exposure.

Response:

- Structured `MentorChatOutput` with `answer`.
- Non-streaming response.

Fallback:

- If analysis is not completed STARTUP_VKR or no result exists, frontend/backend can fall back to mock-style answers.

Current limitations:

- Fragment retrieval is simple term scoring, not RAG/embeddings.
- Chat response can still be limited by structured output/provider behavior; keep answers concise.

## 18. Digital Mascot / Avatar

Current implementation:

- Mascot is image-based, not 3D/Live2D.
- Main actual asset present: `frontend/src/assets/mascot/finik-kosmonavt.png`.
- `mascot-default.png` exists.
- `config.js` references several GIF states, but those GIF files are not currently present in the asset tree.

States:

- idle
- uploading
- thinking
- speaking
- success
- error

Fallback chain:

- Mascot controller can fall back through configured assets and CSS placeholder.

Speech integration:

- UI switches mascot state to speaking while TTS/browser speech runs.
- Remote TTS only speaks final summary when an analysis id is available.

## 19. TTS

TTS is an independent optional layer. It must never change `analysis.status` and must never fail the analysis.

Main provider:

- Polza.ai.
- Model env `TTS_MODEL`, default `openai/gpt-4o-mini-tts`.
- Voice env `TTS_VOICE`, default `verse`.
- Speed env `TTS_SPEED`, default `1.3`.

Actual flow:

```text
MentorReport / demo_report
  -> spoken_summary
  -> TtsService.synthesize_analysis_summary
  -> Polza /audio/speech
  -> storage/audio/analysis_{analysis_id}.mp3
  -> /api/v1/media/audio/{audio_id}
  -> frontend Audio playback
```

Endpoints:

- `POST /api/v1/tts`
- `POST /api/v1/tts/analyses/{analysis_id}`
- `GET /api/v1/media/audio/{audio_id}`

Caching:

- Analysis summary audio id: `analysis_{analysis_id}`.
- If `storage/audio/analysis_{analysis_id}.mp3` exists and is non-empty, no provider call is made.

Retry:

- `TTS_MAX_RETRIES`, default 2.
- Retries httpx timeout/connect/network/remote protocol and statuses 408, 429, 500, 502, 503.
- Does not retry 400, 401, 403, 404.

Timeout:

- `TTS_TIMEOUT_SECONDS`, default 20.

Fallback:

- Missing text/key/provider failure returns `status="fallback"`, `provider="browser"`, `source="browser"`.
- Frontend then uses browser SpeechSynthesis.

Logging:

- Logs model, voice, speed, latency_ms, attempts, status, error_code, audio_duration, source.
- Does not log API key or full text.

## 20. STT

Current state:

- Browser-only voice input through `SpeechRecognition` / `webkitSpeechRecognition`.
- Implemented in `BrowserSttService`.
- Language `ru-RU`, non-continuous, interim results enabled.
- Server-side STT is NOT IMPLEMENTED.
- HTTPS is needed for reliable microphone access in browsers.

Backend `backend/app/services/stt.py` only defines protocol and `SttResult`; no production provider is wired.

## 21. Database

Main SQLAlchemy entities:

- `Document`: uploaded file metadata, storage path, extraction path/status, soft delete.
- `Analysis`: user-visible analysis job, mode, methodology fields, status/progress/current_step.
- `AnalysisEvent`: progress/event stream rows for analysis.
- `AnalysisResult`: one JSON result payload per analysis.
- `DetailedReport`: async detailed PDF status, report id/url/progress.
- `ChatMessage`: chat messages per analysis.
- `LLMCall`: LLM tracing, model/provider/tokens/cost/latency/status and links.
- `Methodology`: methodology code/version/source/demo/active.
- `MethodologyCriterion`: criteria under methodology.
- `MethodologyIndicator`: indicators under criteria.
- `PromptTemplate`: DB prompts by methodology/stage/version.
- `MethodologyAgent`: configured agents and model roles per methodology.
- `Assessment`: methodology execution object for a document/artifact.
- `AssessmentResult`: grouped criterion result.
- `IndicatorResult`: worker indicator result with evidence/recommendations and LLM link.
- `AssessmentTaskRun`: worker task run status/idempotency/error/LLM link.
- `AgentTaskRun`: agent run status/idempotency/error/LLM link.
- `AgentResult`: structured saved output per agent run.
- `GateDecision`: gate status and decision source.
- `MentorAnalysisResult`: combined user report and technical result for STARTUP_VKR.

## 22. Alembic

Current migrations:

- `0001_initial` — initial schema.
- `0002_add_llm_calls` — LLM call trace table.
- `0003_add_methodology_domain` — methodology, criteria, indicators, prompt templates.
- `0004_add_assessment_execution` — assessment execution persistence.
- `0005_add_startup_vkr_agent_flow` — STARTUP_VKR agents/results/gates flow.
- `0006_tune_startup_vkr_prompts` — prompt tuning.
- `0007_startup_vkr_p112_report` — STARTUP_VKR P1.12 methodology/report version.
- `0008_add_analysis_mode` — `Analysis.mode`.
- `0009_add_detailed_reports` — async detailed report table.
- `0010_startup_vkr_regulation_2_0` — STARTUP_VKR 2.0 regulation methodology, criteria, indicators, prompts and agents.

Startup applies migrations automatically in backend container.

## 23. Storage

Runtime storage root is `STORAGE_PATH`, default `/app/storage` in Docker.

Actual/lazy directories:

- `storage/documents/` — uploaded PDF/DOCX files under UUID names.
- `storage/extracted/{document_id}/content.json` — extracted document text.
- `storage/reports/{analysis_id}/{report_id}.pdf` — generated PDFs.
- `storage/audio/` — generated lazily by TTS service; contains MP3 files such as `analysis_{analysis_id}.mp3`.

Storage is mounted into backend container by docker compose:

```text
./storage:/app/storage
```

## 24. API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | basic health |
| GET | `/health/live` | liveness |
| GET | `/health/ready` | readiness plus env/mode summary |
| GET | `/api/v1/config` | public frontend config |
| POST | `/api/v1/documents` | upload and extract PDF/DOCX |
| GET | `/api/v1/documents/{document_id}` | document metadata |
| GET | `/api/v1/documents/{document_id}/content` | extracted content JSON |
| DELETE | `/api/v1/documents/{document_id}` | soft delete and storage cleanup |
| POST | `/api/v1/analyses` | create analysis, starts background task |
| GET | `/api/v1/analyses/{analysis_id}` | analysis status/progress |
| GET | `/api/v1/analyses/{analysis_id}/events` | SSE events |
| GET | `/api/v1/analyses/{analysis_id}/result` | frontend-compatible result |
| POST | `/api/v1/analyses/{analysis_id}/cancel` | cancel queued/processing analysis |
| POST | `/api/v1/analyses/{analysis_id}/reports` | create immediate PDF report |
| GET | `/api/v1/analyses/{analysis_id}/reports/{report_id}` | download PDF report |
| POST | `/api/v1/analyses/{analysis_id}/detailed-report` | start async detailed PDF |
| GET | `/api/v1/analyses/{analysis_id}/detailed-report/status` | detailed PDF status |
| GET | `/api/v1/analyses/{analysis_id}/detailed-report/download` | download detailed PDF |
| GET | `/api/v1/assessments/{assessment_id}/result` | student-facing assessment result |
| GET | `/api/v1/assessments/{assessment_id}/progress` | user progress stages |
| POST | `/api/v1/chat/messages` | mentor chat |
| POST | `/api/v1/tts` | legacy/ad-hoc TTS |
| POST | `/api/v1/tts/analyses/{analysis_id}` | TTS for saved spoken summary |
| GET | `/api/v1/media/audio/{audio_id}` | serve MP3 |
| POST | `/api/v1/internal/assessment` | create assessment internally |
| POST | `/api/v1/internal/pipeline/build` | build pipeline plan |
| POST | `/api/v1/internal/assessments/{assessment_id}/execute` | execute assessment |
| GET | `/api/v1/internal/assessments/{assessment_id}/execution` | execution status |
| GET | `/api/v1/internal/assessments/{assessment_id}/indicator-results` | worker indicator results |
| GET | `/api/v1/internal/assessments/{assessment_id}/gates/current` | current gate |
| POST | `/api/v1/internal/assessments/{assessment_id}/gates/{gate_code}/approve` | approve gate |
| POST | `/api/v1/internal/assessments/{assessment_id}/gates/{gate_code}/return` | return gate |
| POST | `/api/v1/internal/assessments/{assessment_id}/resume` | resume execution |
| POST | `/api/v1/internal/assessments/{assessment_id}/retry-failed` | retry failed execution |
| GET | `/api/v1/internal/assessments/{assessment_id}/technical-result` | internal trace/result |
| POST | `/api/v1/internal/llm/test` | LLM test and trace |
| POST | `/api/v1/internal/methodologies` | import methodology |
| GET | `/api/v1/internal/methodologies` | list methodologies |
| GET | `/api/v1/internal/methodologies/{code}` | get methodology by code |

## 25. Environment Variables

Safe names only; do not store real values in git.

- `APP_ENV` — environment label.
- `LOG_LEVEL` — logging level.
- `DEMO_MODE` — frontend sends demo mode when true.
- `PRESENTATION_MODE` — larger presentation UI mode.
- `POSTGRES_DB` — DB name.
- `POSTGRES_USER` — DB user.
- `POSTGRES_PASSWORD` — DB password, secret in real deployments.
- `DATABASE_URL` — async SQLAlchemy database URL, secret in real deployments.
- `STORAGE_PATH` — runtime storage root.
- `MAX_UPLOAD_SIZE_MB` — upload size limit.
- `ALLOWED_FILE_TYPES` — comma-separated extensions.
- `MOCK_ANALYSIS_ENABLED` — legacy/mock behavior flag.
- `MOCK_ANALYSIS_STEP_DELAY` — mock step delay.
- `CORS_ORIGINS` — allowed CORS origins.
- `FRONTEND_MOCK_MODE` — frontend autonomous mock mode.
- `TTS_MODE` — `remote`, `browser`, or `disabled`.
- `TTS_MAX_TEXT_LENGTH` — spoken summary max chars.
- `TTS_MODEL` — remote TTS model.
- `TTS_VOICE` — remote TTS voice.
- `TTS_SPEED` — remote TTS speed.
- `TTS_TIMEOUT_SECONDS` — remote TTS timeout.
- `TTS_MAX_RETRIES` — remote TTS retry count.
- `DOCUMENT_RETENTION_HOURS` — cleanup config.
- `AUDIO_RETENTION_MINUTES` — cleanup config.
- `REPORT_RETENTION_HOURS` — cleanup config.
- `POLZA_API_KEY` — secret API key.
- `POLZA_BASE_URL` — Polza.ai base URL.
- `LLM_REQUEST_TIMEOUT_SECONDS` — LLM request timeout.
- `ANALYSIS_ENGINE` — `mock`, `assessment_worker`, or `startup_vkr_agents`.
- `AI_DOCUMENT_MAX_CHARS` — standard worker document context limit.
- `AI_DOCUMENT_EXCERPT_STRATEGY` — currently `head_tail`.
- `AI_WORKER_TEMPERATURE`
- `AI_WORKER_MAX_COMPLETION_TOKENS`
- `AI_WORKER_SEED`
- `AI_CRITIC_TEMPERATURE`
- `AI_CRITIC_MAX_COMPLETION_TOKENS`
- `AI_FINAL_EXPERT_TEMPERATURE`
- `AI_FINAL_EXPERT_MAX_COMPLETION_TOKENS`
- `AI_EXECUTION_STOP_ON_ERROR`
- `AI_DEMO_AUTO_APPROVE_GATES`
- `MENTOR_BLOCK_VISIBLE_TO_STUDENT`
- `AI_ASSESSMENT_MAX_COST_RUB`
- `AI_MAX_WORKER_CALLS`
- `AI_MAX_CRITIC_CALLS`
- `AI_MAX_FINAL_EXPERT_CALLS`

## 26. Docker / Deployment

Compose services:

- `frontend`: nginx 1.27 alpine, exposes host port 8080 to container port 80, proxies `/api/` and `/health` to backend.
- `backend`: Python 3.12 slim, installs `backend/requirements.txt`, runs Alembic then uvicorn, exposes container port 8000.
- `db`: PostgreSQL 16 alpine with persistent named volume `postgres_data`.

Volumes:

- `./storage:/app/storage` for backend runtime files.
- `postgres_data:/var/lib/postgresql/data` for DB.

Healthchecks:

- Frontend checks local `/health/live`.
- Backend checks `http://127.0.0.1:8000/health/ready`.
- DB uses `pg_isready`.

Secrets:

- Real `.env` must stay local and must not be committed.
- Do not bake `.env` or API keys into images.

## 27. Tests

Backend:

- pytest with `pytest-asyncio`.
- Test DB is SQLite in-memory.
- Test storage is a temp dir.
- LLM calls are mocked/faked in normal tests; pytest must not call real Polza.ai.

Main suites:

- `backend/tests/test_api.py`
- `backend/tests/test_execution.py`
- `backend/tests/test_llm_client.py`
- `backend/tests/test_startup_vkr_flow.py`
- `backend/tests/test_tts_service.py`

Frontend:

- `frontend/tests/smoke.mjs` static checks for key UI elements, TTS fallback, mascot fallback, demo docs.

Commands:

```bash
cd backend && ../.venv/bin/python -m pytest
node frontend/tests/smoke.mjs
make test
```

Smoke scripts:

- `scripts/test_assessment_worker.py`
- `scripts/test_startup_vkr_e2e.py`

## 28. Logging / Observability

Implemented observability:

- `llm_calls` table records model, provider, tokens, cost, latency, status, and links to analysis/assessment/task/agent/prompt/criterion/indicator.
- `AnalysisEvent` records progress and user-facing messages.
- `AgentTaskRun` and `AssessmentTaskRun` record start/end timestamps, status, errors, idempotency.
- Demo mode logs `startup_vkr_demo_completed` with total tokens, processing_time_ms, agent_time_a15/a16/a17/a28/a01.
- TTS logs model, voice, speed, latency, attempts, status, error_code, audio_duration, source.
- Startup logs interrupted queued/processing analyses.

Useful performance queries should compare:

- first and last `AgentTaskRun.started_at/completed_at`;
- `LLMCall.latency_ms`;
- `LLMCall.prompt_tokens/completion_tokens/cost_rub`;
- demo agent start spread to verify parallelism.

## 29. Known Issues / Technical Debt

- README is partly outdated and still mentions some old stub/real-LLM limitations; use code and this file as current context.
- `StubFileSecurityService` is not production antivirus.
- OCR is not implemented.
- Browser STT only; no backend STT provider.
- Mascot config references GIF assets that are not present in current asset tree.
- Standard/full STARTUP_VKR critic stage is sequential, while demo critic agents are parallel.
- Demo agent failures can still fail the full demo analysis; only demo final has deterministic fallback.
- Detailed report is not a separate deep AI report; it is a PDF assembly from saved result and extracted fragments.
- Fragment search for chat/report is simple keyword scoring, not semantic retrieval.
- Auth/roles/admin access are not implemented; internal endpoints are exposed at API level.
- Analysis history is server-backed through `GET /api/v1/analyses/history`; without auth it is intentionally shared across the current deployment rather than isolated per user.
- Long/complex documents can still stress structured output limits if prompts or completion caps are changed carelessly.
- Some legacy DTO fields (`overall_score`, 0-100 criteria) remain for backward frontend compatibility.

## 30. Последние ключевые решения

1. Мультиагентность сохраняется.
2. Polza.ai is the current LLM/TTS aggregator.
3. Mistral, Claude, and GPT have different roles.
4. Demo mode must be fast but multi-agent.
5. Expert/full methodology is not deleted.
6. User-facing report must not be raw LLM trace.
7. Scores are needed for demo/university scenario.
8. Long text in frontend should be visually contained or expanded cleanly, not break layout.
9. TTS is independent and optional.
10. TTS failure must not break analysis.
11. Secrets are never hardcoded.
12. New methodologies should go through the existing methodology layer, not isolated hardcoded pipelines.
13. A-01 is the single external voice; users should not see raw internal agent names by default.
14. Demo detailed report generation should not block fast result.

## 31. Что нельзя делать без явного запроса

Do NOT:

- Rewrite architecture from scratch.
- Replace FastAPI.
- Replace PostgreSQL.
- Remove multi-agent architecture.
- Collapse all roles into one generic LLM.
- Change Polza.ai provider without a task.
- Delete expert/full pipeline.
- Hardcode API keys or secrets.
- Commit `.env`.
- Delete old methodology versions.
- Break backward compatibility without a concrete reason.
- Create new abstraction layers just because the current code is imperfect.
- Add LangChain/LangGraph/CrewAI only for framework usage.
- Turn demo optimization into a full rewrite.
- Send raw PDF/DOCX directly to LLM.
- Expose internal model/provider/token/cost details in student-facing reports.

## 32. Правила дальнейшей разработки

Before implementing:

1. Read `AGENTS.md`.
2. Read this `MASTER_CONTEXT.md`.
3. Check `git status`.
4. Inspect the files relevant to the task.
5. Prefer existing services/schemas/executors.
6. Treat current code as source of truth if docs conflict.

During implementation:

- Keep changes targeted.
- Do not mix unrelated refactors.
- Preserve architecture and methodology versioning.
- Add Alembic migration for schema changes.
- Use mock/fake LLM in ordinary tests.
- Avoid logging secrets, full prompts, full documents, or API keys.

After implementation:

- Run relevant pytest suites.
- Run frontend smoke if UI changes.
- Check migrations.
- Check `docker compose config` or build when deployment behavior changes.
- Update this file after significant architecture changes.

## 33. Ближайший roadmap

NOW:

- Stabilize demo mode structured outputs across varied document sizes.
- Keep UI readable with no clipped text or broken cards.
- Verify remote TTS uses cached MP3 and only final `spoken_summary`.
- Keep detailed report and chat grounded in extracted text.

NEXT:

- Make detailed report richer without blocking quick demo result.
- Improve evidence linking and fragment retrieval for chat/report.
- Add a real file security provider.
- Harden internal endpoints before real production exposure.
- Add more regression tests around frontend result rendering and TTS states.

LATER:

- OCR for scanned PDFs.
- Server-side STT.
- Auth/users/roles.
- Production human gate/signature workflow.
- Full S0-S9 state machine if required by product scenario.
- Semantic retrieval/RAG only if explicitly requested and justified.
- 3D/Live2D avatar only if it becomes a product requirement.

## 34. Как начать новую сессию Codex

Перед любой работой:

1. Прочитай `AGENTS.md`.
2. Прочитай `MASTER_CONTEXT.md`.
3. Проверь `git status`.
4. Изучи файлы, относящиеся к задаче.
5. Не полагайся только на `MASTER_CONTEXT.md`: если код ему противоречит, код является источником истины.
6. Не начинай с переписывания архитектуры; сначала найди существующий flow и точку минимального изменения.

## 35. Demo UX, history, evidence navigation, and metrics

- Mascot text is a compact status/preview surface; full mentor answers remain in chat while TTS still receives the complete spoken text.
- Frontend progress separates saved backend stages from smooth visual interpolation. Stage ceilings prevent 100% before real completion; the UI also shows elapsed time and respects reduced-motion preferences.
- STARTUP_VKR demo criteria render sentence-safe previews and expandable details with strengths, issues, recommendations, and available evidence.
- `GET /api/v1/analyses/history` lists saved analyses from existing `Analysis`, `Document`, `AnalysisResult`, and `DetailedReport` records. No new history table is used.
- `GET /api/v1/analyses/{analysis_id}/metrics` aggregates saved `llm_calls` and analysis timestamps without returning prompts, responses, or secrets.
- `GET /api/v1/analyses/{analysis_id}/evidence` maps saved agent evidence to extracted PDF blocks or DOCX paragraphs. PDF evidence can navigate to a real source page; DOCX uses an extracted-fragment panel because no page mapping exists.
- `GET /api/v1/documents/{document_id}/source` serves the retained original document inline for the evidence viewer.
- History uses a bounded modal scroll area so long server-backed lists remain usable on laptop-sized screens.
- PDF evidence uses `GET /api/v1/documents/{document_id}/pages/{page_number}/preview` to render the real retained source page with PyMuPDF; the frontend positions a visible highlight from the extracted block `bbox` and stored page dimensions.
- The demo report overview includes project readiness, six compact score indicators, richer criterion cards, and persistent per-analysis recommendation planning stored in browser localStorage. This planning progress does not affect AI scoring.
- Generated PDF reports use branded page bands, section panels, and compact item cards while preserving the same saved report content.
- No database migration, new LLM call, methodology/scoring change, model change, or TTS configuration change was required.
