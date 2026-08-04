# Цифровой ментор

Технический контур демонстрационной системы для анализа учебных и проектных работ. Интерфейс остается статическим vanilla HTML/CSS/JavaScript, но загрузка файлов, хранение, прогресс анализа, результат и чат теперь проходят через backend API.

Реальная методология анализа, LLM, ИИ-агенты, ИИ-жюри, OCR, Live2D/3D-аватар и production TTS/STT на этом этапе не подключены.

## Архитектура

```text
frontend/         статический интерфейс, nginx, proxy /api и /health
backend/          FastAPI, SQLAlchemy, Alembic, mock analysis engine
storage/          локальное файловое хранилище документов, извлеченного текста и отчетов
docker-compose.yml
.env.example
```

Контейнеры:

- `frontend` - nginx со статическим UI и proxy на backend;
- `backend` - FastAPI под `uvicorn`;
- `db` - PostgreSQL 16 с persistent volume.

## Запуск

```bash
cp .env.example .env
docker compose up --build
```

Открыть:

```text
http://localhost:8080/
```

Для legacy Compose:

```bash
docker-compose up --build
```

## Переменные окружения

См. `.env.example`.

Основные переменные:

- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`;
- `DATABASE_URL`;
- `STORAGE_PATH`;
- `MAX_UPLOAD_SIZE_MB`;
- `ALLOWED_FILE_TYPES`;
- `MOCK_ANALYSIS_ENABLED`;
- `MOCK_ANALYSIS_STEP_DELAY`;
- `CORS_ORIGINS`;
- `LOG_LEVEL`.

Реальный `.env` не коммитится.

## API

- `GET /health`
- `POST /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `POST /api/v1/analyses`
- `GET /api/v1/analyses/{analysis_id}`
- `GET /api/v1/analyses/{analysis_id}/result`
- `GET /api/v1/analyses/{analysis_id}/events`
- `POST /api/v1/analyses/{analysis_id}/cancel`
- `POST /api/v1/chat/messages`

## Хранение

Оригинальные PDF/DOCX сохраняются в `storage/documents/` под UUID-именами. Извлеченный текст сохраняется в `storage/extracted/{document_id}/content.json`. Файлы не доступны напрямую из frontend.

PDF извлекается через PyMuPDF с сохранением страниц и блоков. DOCX извлекается через `python-docx` с сохранением абзацев и стилей. OCR не реализован; PDF без текстового слоя возвращает `DOCUMENT_TEXT_NOT_FOUND`.

## Mock-Режим

Основной режим frontend работает через backend API. Аварийный frontend mock-режим можно включить через:

```javascript
window.__DIGITAL_MENTOR_CONFIG__ = { mockMode: true };
```

или через query/localStorage в `frontend/src/js/config.js`.

Backend использует `MockAnalysisEngine`. Он пишет статусы, события, прогресс и итоговый mock-результат в PostgreSQL. Позже его нужно заменить на `MethodologyAnalysisEngine` через тот же контракт, без изменения frontend API.

## Голос И Маскот

Маскот управляется отдельным frontend-модулем. Поддерживаются состояния `idle`, `uploading`, `thinking`, `speaking`, `success`, `error`.

Поиск ассетов идет по цепочке:

```text
mascot-idle.gif
mascot-thinking.gif
mascot-speaking.gif
mascot-success.gif
mascot-error.gif
mascot-default.gif
mascot-default.png
finik-kosmonavt.png
```

Озвучивание работает через browser SpeechSynthesis как fallback. Голосовой ввод работает через browser SpeechRecognition как fallback. Для надежной работы микрофона на сервере потребуется HTTPS, который должен быть настроен внешним reverse proxy.

## Тесты

Локально:

```bash
cd backend
../.venv/bin/python -m pytest
```

В контейнере:

```bash
docker compose run --rm backend pytest
```

## Развертывание На Сервере

1. Клонировать репозиторий.
2. Создать `.env` на основе `.env.example` и заменить пароль PostgreSQL.
3. Создать/оставить каталоги `storage/documents`, `storage/extracted`, `storage/reports`.
4. Запустить `docker compose up -d --build`.
5. Открыть порт `8080` или прокинуть его через внешний nginx/reverse proxy.
6. Для HTTPS и микрофона настроить TLS на внешнем reverse proxy.

## Точки Будущей Интеграции

- AI workflow: `backend/app/services/analysis_engine.py`, `backend/app/services/mock_analysis_engine.py`.
- Документная методология: `POST /api/v1/analyses` и поля `analysis_type`, `methodology_id`, `methodology_version`.
- TTS: `frontend/src/js/modules/speech.js`, будущий `RemoteTtsSpeechService`.
- STT: `frontend/src/js/modules/speech.js`, будущий remote STT provider.
- Маскот/аватар: `frontend/src/js/modules/mascot.js`.
- Хранилище S3: `backend/app/services/storage.py`.
- Антивирусная проверка: `backend/app/services/security.py`.
