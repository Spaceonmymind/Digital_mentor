# Digital Mentor: инструкция по развёртыванию и передаче проекта

Документ предназначен для коллег, которые получают репозиторий Digital Mentor и должны развернуть его на Linux-сервере. Основной поддерживаемый способ запуска — Docker Compose.

## 1. Что входит в решение

Приложение состоит из трёх контейнеров:

- `digital-mentor-frontend` — nginx со статическим frontend, внешний порт `8080`;
- `digital-mentor-backend` — FastAPI, доступен frontend-контейнеру на внутреннем порту `8000`;
- `digital-mentor-db` — PostgreSQL 16 с постоянным Docker volume `postgres_data`.

Пользовательские файлы, извлечённый текст, отчёты и сгенерированное аудио хранятся в каталоге `storage/` на сервере. Миграции Alembic автоматически выполняются при запуске backend.

## 2. Ограничения текущей версии

Перед публикацией сервиса необходимо учитывать:

- в приложении пока нет пользователей, ролей и production-аутентификации;
- endpoints `/api/v1/internal/*` не защищены отдельной авторизацией;
- антивирусная проверка файлов является заглушкой;
- OCR отсутствует: сканированные PDF без текстового слоя не анализируются;
- история анализов общая для текущего deployment;
- данные хранятся локально и требуют отдельной политики резервного копирования;
- Polza.ai является внешним обработчиком AI-запросов.

До появления аутентификации сервис следует размещать во внутренней сети, за VPN или за внешним reverse proxy с контролем доступа. Не рекомендуется открывать порт `8080` напрямую в Интернет.

## 3. Требования к серверу

Обязательно:

- Linux x86_64 или ARM64;
- Docker Engine;
- Docker Compose v2 (`docker compose`);
- Git;
- доступ к `https://polza.ai` по TCP/443;
- DNS и корректное системное время;
- открытые внешние порты 80/443 для HTTPS reverse proxy;
- постоянное место на диске для PostgreSQL и `storage/`.

Для пилотного стенда разумная стартовая конфигурация — 2 vCPU, 4 GB RAM и не менее 20 GB свободного диска. Требования к диску зависят от числа и размера документов.

Проверка окружения:

```bash
docker --version
docker compose version
git --version
curl -I https://polza.ai
```

## 4. Получение проекта

```bash
git clone <REPOSITORY_URL> Digital_mentor
cd Digital_mentor
git switch feature/startup-vkr-agent-flow
```

Если коллегам передаётся релизный tag или отдельная production-ветка, вместо указанной ветки необходимо выбрать согласованный tag/branch.

Проверить полученную версию:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
```

## 5. Настройка `.env`

Создать локальный конфигурационный файл:

```bash
cp .env.example .env
chmod 600 .env
```

Файл `.env` запрещено коммитить, пересылать в открытых чатах или включать в Docker image. Значение `POLZA_API_KEY` следует передать коллегам через согласованный защищённый канал.

Минимальные production-настройки:

```dotenv
APP_ENV=production
LOG_LEVEL=INFO

POSTGRES_DB=digital_mentor
POSTGRES_USER=digital_mentor
POSTGRES_PASSWORD=<STRONG_RANDOM_PASSWORD>
DATABASE_URL=postgresql+asyncpg://digital_mentor:<URL_ENCODED_PASSWORD>@db:5432/digital_mentor

POLZA_API_KEY=<POLZA_API_KEY>
POLZA_BASE_URL=https://polza.ai/api/v1

ANALYSIS_ENGINE=startup_vkr_agents
DEMO_MODE=true
FRONTEND_MOCK_MODE=false
MOCK_ANALYSIS_ENABLED=false

CORS_ORIGINS=https://<PUBLIC_DOMAIN>
STORAGE_PATH=/app/storage
MAX_UPLOAD_SIZE_MB=50
ALLOWED_FILE_TYPES=.pdf,.docx
```

Важно:

- пароль внутри `DATABASE_URL` должен совпадать с `POSTGRES_PASSWORD`;
- специальные символы в пароле внутри URL необходимо URL-кодировать;
- `ANALYSIS_ENGINE=mock` из `.env.example` не запускает реальный мультиагентный анализ;
- `ANALYSIS_ENGINE=startup_vkr_agents` включает рабочий STARTUP_VKR pipeline через Polza.ai;
- `DEMO_MODE=true` включает быстрый мультиагентный demo-flow;
- для standard/expert анализа frontend должен передавать соответствующий mode;
- `CORS_ORIGINS=*` допустим только для изолированного тестового стенда.

Frontend использует четыре заранее записанных WAV-файла:

```text
frontend/src/assets/audio/greeting.wav
frontend/src/assets/audio/uploading.wav
frontend/src/assets/audio/analysis.wav
frontend/src/assets/audio/completed.wav
```

Если нужны только эти записанные фразы, можно установить:

```dotenv
TTS_MODE=disabled
```

Backend TTS является необязательной функцией и не должен влиять на результат анализа.

Проверить итоговую Compose-конфигурацию без вывода её в общий лог:

```bash
docker compose config --quiet
```

Не публикуйте полный вывод `docker compose config`: в нём окажется раскрытое значение `POLZA_API_KEY`.

## 6. Первый запуск

```bash
mkdir -p storage/documents storage/extracted storage/reports storage/audio
docker compose up -d --build
docker compose ps
```

Backend при старте самостоятельно выполняет:

```text
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Посмотреть запуск без вывода секретов:

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=100 frontend
docker compose logs --tail=100 db
```

Все три сервиса должны перейти в состояние `healthy`.

## 7. Проверка работоспособности

С самого сервера:

```bash
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8080/health/ready
curl -fsS http://127.0.0.1:8080/api/v1/config
curl -fsSI http://127.0.0.1:8080/
```

Ожидается:

- `/health/live` — HTTP 200;
- `/health/ready` — HTTP 200 и готовность БД;
- `/api/v1/config` — `demo_mode`, `frontend_mock_mode` и `tts_mode` без секретов;
- `/` — frontend HTML.

Проверить применённую миграцию:

```bash
docker compose exec -T backend alembic current
```

Проверить логи на ошибки:

```bash
docker compose logs --since=10m backend | grep -Ei 'error|exception|traceback' || true
```

После технической проверки необходимо вручную загрузить тестовый PDF/DOCX через UI и убедиться, что:

1. документ загружается и извлекается текст;
2. анализ завершается;
3. результат и критерии отображаются;
4. исходный документ/фрагменты открываются;
5. PDF-отчёт скачивается;
6. чат отвечает по сохранённому анализу;
7. четыре записанные голосовые фразы воспроизводятся по одному разу.

## 8. HTTPS и внешний nginx

Готовый шаблон находится в:

```text
deploy/nginx/digital-mentor.conf.example
```

Порядок настройки:

1. Скопировать шаблон в конфигурацию системного nginx.
2. Заменить `mentor.example.fa.ru` на реальный домен.
3. Выпустить TLS-сертификат и указать корректные пути к нему.
4. Проксировать внешний HTTPS на `127.0.0.1:8080`.
5. Ограничить доступ к порту `8080` системным firewall.
6. При внешней публикации добавить VPN, SSO или Basic Auth до появления встроенной авторизации.

Пример установки:

```bash
sudo cp deploy/nginx/digital-mentor.conf.example /etc/nginx/sites-available/digital-mentor.conf
sudo ln -s /etc/nginx/sites-available/digital-mentor.conf /etc/nginx/sites-enabled/digital-mentor.conf
sudo nginx -t
sudo systemctl reload nginx
```

Микрофон браузера для голосового ввода надёжно работает только через HTTPS.

## 9. Обновление версии

Перед обновлением сохранить backup и зафиксировать текущий commit:

```bash
cd ~/Digital_mentor
git rev-parse HEAD
./scripts/backup.sh
```

Затем:

```bash
git pull --ff-only origin feature/startup-vkr-agent-flow
docker compose config --quiet
docker compose build --pull
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:8080/health/ready
docker compose logs --tail=200 backend
```

Миграции применяются автоматически во время запуска backend. Не запускайте несколько обновляющихся backend-экземпляров одновременно без отдельной схемы миграций.

Для изменений только frontend можно пересобрать его отдельно:

```bash
docker compose build frontend
docker compose up -d --no-deps frontend
```

Для изменений backend:

```bash
docker compose build backend
docker compose up -d --no-deps backend
```

## 10. Backup

Встроенная команда:

```bash
./scripts/backup.sh
```

Она сохраняет:

- PostgreSQL dump в `backups/<timestamp>/postgres.sql`;
- `storage/reports` в `backups/<timestamp>/reports.tar.gz`.

Она **не сохраняет** оригиналы документов, extracted JSON и аудио. Если политика хранения требует полного восстановления, дополнительно сохраняйте весь `storage/`:

```bash
tar -czf "backups/storage-$(date +%Y%m%d-%H%M%S).tar.gz" storage
```

Каталог `backups/` должен регулярно копироваться за пределы сервера и храниться зашифрованно, поскольку dump и документы могут содержать пользовательские данные.

Периодически проверяйте не только создание архива, но и тестовое восстановление на отдельном стенде.

## 11. Восстановление

Базовая команда проекта:

```bash
./scripts/restore.sh backups/YYYYMMDD-HHMMSS
```

Восстановление следует выполнять в согласованное окно обслуживания. Скрипт импортирует dump в текущую БД и распаковывает отчёты; он не очищает существующую БД автоматически. Для production сначала подготовьте пустую БД либо используйте отдельно проверенную процедуру восстановления.

Если имеется полный архив `storage/`, его следует восстановить в корень проекта с сохранением владельца и прав, затем перезапустить сервисы и проверить health endpoints.

## 12. Rollback

Откат приложения без отката схемы БД:

```bash
git switch --detach <PREVIOUS_COMMIT_OR_TAG>
docker compose up -d --build
```

Но этот способ безопасен только если старая версия совместима с уже применённой схемой БД. Alembic migration может сделать простой checkout недостаточным. Для полного rollback используйте backup БД, созданный перед обновлением, и заранее проверенную процедуру восстановления.

После устранения проблемы вернитесь на рабочую ветку/tag, а не продолжайте разработку в detached HEAD.

## 13. Эксплуатационные команды

```bash
# Состояние сервисов
docker compose ps

# Все последние логи
docker compose logs --tail=200

# Следить за backend
docker compose logs -f backend

# Перезапустить один сервис
docker compose restart backend

# Остановить контейнеры, сохранив данные
docker compose down

# Запустить снова
docker compose up -d

# Размер пользовательского хранилища
du -sh storage

# Размер Docker volume PostgreSQL
docker system df -v
```

Не используйте `docker compose down -v` в production: команда удалит PostgreSQL volume.

Не запускайте `scripts/reset-demo.sh` на production: скрипт удаляет БД и файлы из `storage/`.

## 14. Частые проблемы

### Сайт не открывается

```bash
docker compose ps
ss -lntp | grep -E ':8080|:80|:443'
curl -v http://127.0.0.1:8080/health/live
docker compose logs --tail=100 frontend
```

Проверить firewall, внешний nginx, DNS домена и TLS-сертификат.

### Backend не становится healthy

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=100 db
docker compose exec -T db pg_isready -U digital_mentor -d digital_mentor
```

Частые причины: неверный `DATABASE_URL`, несовпадающий пароль, нехватка диска или ошибка миграции.

### Анализ не запускается или используется mock

Проверить только безопасные настройки:

```bash
docker compose exec -T backend sh -lc \
  'printf "ANALYSIS_ENGINE=%s\nDEMO_MODE=%s\nFRONTEND_MOCK_MODE=%s\n" \
  "$ANALYSIS_ENGINE" "$DEMO_MODE" "$FRONTEND_MOCK_MODE"'
```

Для реального demo ожидается:

```text
ANALYSIS_ENGINE=startup_vkr_agents
DEMO_MODE=true
FRONTEND_MOCK_MODE=false
```

Не печатайте `POLZA_API_KEY` и полный environment контейнера.

### Polza.ai недоступен

```bash
docker compose exec -T backend python -c \
  "import socket; print(socket.getaddrinfo('polza.ai', 443, type=socket.SOCK_STREAM))"
```

Проверить исходящий TCP/443, DNS, VPN/proxy и логи backend. Не использовать `/chat/completions` для обычной сетевой диагностики: это создаёт реальный inference-вызов и расход.

### Закончился диск

```bash
df -h
du -sh storage backups
docker system df
```

Перед удалением данных обязательно создать backup и согласовать retention policy.

## 15. Что передать коллегам

Передача считается полной, когда коллеги получили:

- URL Git-репозитория и точный branch/tag/commit;
- этот документ;
- публичный домен и информацию о DNS;
- Polza API key через защищённый канал;
- production DB credentials через защищённый канал;
- описание сервера и ответственного администратора;
- правила доступа к VPN/SSH;
- политику backup, retention и обработки пользовательских документов;
- контакты владельца продукта и технического ответственного;
- список известных ограничений из раздела 2.

Контрольный акт приёмки:

```text
[ ] Репозиторий получен, commit зафиксирован
[ ] .env создан локально и имеет права 600
[ ] Секреты не находятся в Git
[ ] docker compose config --quiet проходит
[ ] Все контейнеры healthy
[ ] HTTPS работает
[ ] Порт 8080 не открыт публично
[ ] Реальный demo-анализ завершён
[ ] Отчёт и evidence viewer работают
[ ] Backup создан и тестово восстановлен
[ ] Мониторинг диска и сроков сертификата назначен
[ ] Известные ограничения приняты
```
