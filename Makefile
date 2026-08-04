COMPOSE ?= docker compose

.PHONY: up down build rebuild logs test migrate reset-demo backup restore

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

rebuild:
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d

logs:
	$(COMPOSE) logs --tail=200 -f

test:
	cd backend && ../.venv/bin/python -m pytest

migrate:
	$(COMPOSE) exec backend alembic upgrade head

reset-demo:
	./scripts/reset-demo.sh

backup:
	./scripts/backup.sh

restore:
	./scripts/restore.sh
