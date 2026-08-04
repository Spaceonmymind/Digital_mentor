# Цифровой ментор

Демонстрационный технический контур системы анализа учебных и проектных работ. UI остается vanilla HTML/CSS/JavaScript, а загрузка документов, хранение, извлечение текста, прогресс анализа, результат, чат, TTS stub и PDF-отчет работают через backend API.

Не подключены: реальные LLM, ИИ-агенты, утвержденная методология, ИИ-жюри, OCR, Live2D/3D, production TTS/STT, авторизация и multi-tenant.

## Архитектура

```text
frontend/         nginx + статический UI + proxy /api и /health
backend/          FastAPI + SQLAlchemy + Alembic + MockAnalysisEngine
storage/          documents, extracted, reports, runtime audio
demo/             sample PDF/DOCX без персональных данных
deploy/nginx/     пример внешнего HTTPS reverse proxy
scripts/          управление, backup, restore, reset
docker-compose.yml
.env.example
```

Контейнеры:

- `frontend` - nginx, порт `8080`, статика и proxy;
- `backend` - FastAPI/uvicorn, миграции Alembic перед стартом;
- `db` - PostgreSQL 16 с persistent volume и healthcheck.

## Быстрый Запуск

```bash
cp .env.example .env
docker compose up -d --build
```

Открыть:

```text
http://localhost:8080/
```

Проверки:

```bash
curl -f http://localhost:8080/health/live
curl -f http://localhost:8080/health/ready
curl -f http://localhost:8080/
```

## Команды

```bash
make up
make down
make build
make rebuild
make logs
make test
make migrate
make reset-demo
make backup
make restore
```

Аналоги лежат в `scripts/`.

## Переменные Окружения

См. `.env.example`.

Основные:

- `APP_ENV`, `LOG_LEVEL`, `DEMO_MODE`;
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL`;
- `STORAGE_PATH`, `MAX_UPLOAD_SIZE_MB`, `ALLOWED_FILE_TYPES`;
- `MOCK_ANALYSIS_ENABLED`, `MOCK_ANALYSIS_STEP_DELAY`;
- `FRONTEND_MOCK_MODE`;
- `TTS_MODE`, `TTS_MAX_TEXT_LENGTH`;
- `DOCUMENT_RETENTION_HOURS`, `AUDIO_RETENTION_MINUTES`, `REPORT_RETENTION_HOURS`;
- `CORS_ORIGINS`.

Реальный `.env` не коммитится.

## API

- `GET /health`, `GET /health/live`, `GET /health/ready`
- `GET /api/v1/config`
- `POST /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `GET /api/v1/documents/{document_id}/content`
- `DELETE /api/v1/documents/{document_id}`
- `POST /api/v1/analyses`
- `GET /api/v1/analyses/{analysis_id}`
- `GET /api/v1/analyses/{analysis_id}/events`
- `GET /api/v1/analyses/{analysis_id}/result`
- `POST /api/v1/analyses/{analysis_id}/cancel`
- `POST /api/v1/analyses/{analysis_id}/reports`
- `GET /api/v1/analyses/{analysis_id}/reports/{report_id}`
- `POST /api/v1/chat/messages`
- `POST /api/v1/tts`
- `GET /api/v1/media/audio/{audio_id}`

Ошибки возвращаются в формате:

```json
{
  "error": {
    "code": "DOCUMENT_TEXT_NOT_FOUND",
    "message": "В документе не найден текстовый слой",
    "details": null,
    "request_id": "uuid"
  }
}
```

`X-Request-ID` принимается из запроса или генерируется backend и возвращается в response headers.

## Документы И Анализ

Поддерживаются `.pdf` и `.docx`, максимум 50 МБ. Проверяются расширение, MIME, сигнатура PDF `%PDF`, DOCX ZIP-структура, размер, пустой файл, SHA-256 и безопасное имя. Файлы сохраняются под UUID-именами в `storage/documents/`.

Извлеченный текст сохраняется в:

```text
storage/extracted/{document_id}/content.json
```

PDF извлекается через PyMuPDF с страницами, блоками и bbox. DOCX извлекается через `python-docx` с абзацами и стилями. OCR не реализован.

`MockAnalysisEngine` пишет progress/events/result в PostgreSQL. Frontend получает прогресс только от backend, кроме явного аварийного `FRONTEND_MOCK_MODE=true`.

## Demo Mode И Mock Mode

`DEMO_MODE=true` включает кнопку "Использовать демонстрационный документ". Документы лежат в `demo/sample-document.pdf` и `demo/sample-document.docx`.

`FRONTEND_MOCK_MODE=true`, `?mock=1` или `localStorage.FRONTEND_MOCK_MODE=true` включает автономный frontend mock-mode. В интерфейсе показывается "Демонстрационный автономный режим".

## Голос И Маскот

TTS режимы:

- `remote` - пробует backend TTS; без провайдера вернется fallback;
- `browser` - browser SpeechSynthesis;
- `disabled` - только текст.

Backend сейчас содержит `StubTtsProvider` и контракт `TtsProvider`. Реальный провайдер подключается позже через `RemoteTtsProvider`.

STT пока работает через browser SpeechRecognition. Микрофон запускается только по действию пользователя. Для надежной работы микрофона на сервере нужен HTTPS.

Маскот поддерживает цепочку:

```text
state GIF -> mascot-default.gif -> mascot-default.png -> finik-kosmonavt.png -> CSS placeholder
```

## Отчеты И Удаление

PDF-отчет формируется backend через `ReportService` и сохраняется в:

```text
storage/reports/{analysis_id}/{report_id}.pdf
```

Удаление документа:

- блокируется при активном анализе без `force=true`;
- логически помечает документ как deleted;
- физически удаляет оригинал и extracted JSON;
- удаляет связанные demo-отчеты.

## Backup

`scripts/backup.sh` сохраняет:

- dump PostgreSQL;
- `storage/reports`.

Документы пользователей в долгосрочный backup не включаются без отдельного требования.

Восстановление:

```bash
scripts/restore.sh backups/YYYYMMDD-HHMMSS
```

## Развертывание На Сервере Финансового Университета

Требования:

- Linux-сервер;
- Docker Engine и Docker Compose;
- открытый порт `80/443` на внешнем reverse proxy;
- локальный порт `8080` для frontend-контейнера;
- persistent volume для PostgreSQL;
- каталог `storage/` на диске сервера.

Порядок:

1. Склонировать репозиторий.
2. Создать `.env` из `.env.example`.
3. Заменить `POSTGRES_PASSWORD` и `DATABASE_URL`.
4. Проверить `docker compose config`.
5. Запустить `docker compose up -d --build`.
6. Проверить `docker compose ps`.
7. Проверить `curl -f http://localhost:8080/health/ready`.
8. Настроить внешний nginx по примеру `deploy/nginx/digital-mentor.conf.example`.
9. Подключить HTTPS-сертификаты вне репозитория.
10. Проверить микрофон в браузере через HTTPS.
11. Настроить backup reports/PostgreSQL.

Обновление версии:

```bash
git pull
docker compose up -d --build
docker compose logs --tail=200
```

Rollback:

```bash
git checkout <previous-commit>
docker compose up -d --build
```

## Тесты

```bash
cd backend
../.venv/bin/python -m pytest
```

Проверяется: health/readiness, загрузка и извлечение PDF/DOCX, отказы некорректных файлов, лимит размера, path traversal имя, Unicode имя, анализ/events/result, cancel, report PDF, delete, TTS stub, chat.

## Точки Будущей Интеграции

- AI workflow: `backend/app/services/analysis_engine.py`;
- замена mock: `backend/app/services/mock_analysis_engine.py` -> `MethodologyAnalysisEngine`;
- S3-хранилище: `backend/app/services/storage.py`;
- антивирус: `backend/app/services/security.py`;
- TTS: `backend/app/services/tts.py`, `frontend/src/js/modules/speech.js`;
- STT: `backend/app/services/stt.py`, `frontend/src/js/modules/speech.js`;
- цифровой аватар: `frontend/src/js/modules/mascot.js`.
