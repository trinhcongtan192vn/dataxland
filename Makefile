# DataxLand – lệnh thường dùng (spec 00 §6).
SHELL := bash
.ONESHELL:
COMPOSE := docker compose -f infra/compose/docker-compose.yml --env-file .env
TENANT ?= demo_seller
PY := uv run

.PHONY: setup up down seed-local dbt-build semantic test test-py test-dbt test-web lint e2e sync-tenants api bot web cube dagster

setup:
	uv sync
	pnpm install
	cd transform && $(PY) dbt deps --profiles-dir .
	[ -f .env ] || cp .env.example .env
	$(PY) python ops/init_local.py

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

seed-local:
	$(PY) python ops/seed_local.py

dbt-build:
	$(PY) python ops/dbt_build.py $(TENANT)

semantic:
	$(PY) python semantic/build.py

sync-tenants:
	$(PY) python ops/sync_tenants.py

test: test-py test-dbt test-web

test-py:
	$(PY) pytest libs services pipelines semantic ops/tests

test-dbt:
	$(PY) python ops/dbt_build.py demo_seller --fixed-samples
	$(PY) python ops/dbt_build.py demo_agency --fixed-samples
	$(PY) pytest transform/tests

test-web:
	pnpm --filter web test
	pnpm --filter web build

lint:
	$(PY) ruff check .
	$(PY) ruff format --check .
	$(PY) mypy libs/dx_common/src services/api/app services/telegram_bot/bot services/mcp/dx_mcp services/identity_worker/identity_worker
	$(PY) python transform/scripts/check_portability.py
	cd transform && $(PY) sqlfluff lint models --dialect bigquery
	$(PY) python -m dx_common.tenants validate tenants/
	pnpm --filter web lint
	pnpm --filter web format:check

e2e:
	pnpm --filter web e2e

# Chạy từng dịch vụ trực tiếp, không cần Docker (xem docs/local-dev.md)
api:
	cd services/api && $(PY) uvicorn app.main:app --reload --port 8000

bot:
	cd services/telegram_bot && $(PY) python -m bot.main

web:
	pnpm --filter web dev

cube:
	cd cube && npm run dev

dagster:
	cd pipelines && $(PY) dagster dev -m dx_pipelines.definitions -p 3001
