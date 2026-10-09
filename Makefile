# ResearchFlow AI developer commands. Run `make help`.
BACKEND := backend
FRONTEND := frontend
PY := $(BACKEND)/.venv/bin/python

.PHONY: help setup db up down migrate backend frontend test test-backend test-frontend lint typecheck eval check

help: ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

setup: ## Create the Python venv and install backend + frontend deps
	test -f .env || cp .env.example .env
	cd $(BACKEND) && python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
	cd $(FRONTEND) && npm install

db: ## Start Postgres + pgvector (host port 5433)
	docker compose up -d db

up: ## Run the whole stack in Docker (db, backend, frontend)
	docker compose up -d --build

down: ## Stop Docker services (data volumes are kept)
	docker compose down

migrate: ## Apply Alembic migrations and LangGraph checkpoint tables
	cd $(BACKEND) && .venv/bin/alembic upgrade head && .venv/bin/python -m scripts.setup_checkpointer

backend: ## Run the API locally with auto-reload (http://localhost:8000/docs)
	cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

frontend: ## Run the Next.js dev server (http://localhost:3000)
	cd $(FRONTEND) && npm run dev

test: test-backend test-frontend ## Run all tests

test-backend: ## Backend tests (needs `make db` for DB/API tests)
	cd $(BACKEND) && .venv/bin/python -m pytest -q

test-frontend: ## Frontend tests (Vitest)
	cd $(FRONTEND) && npm test

lint: ## Lint + format check
	cd $(BACKEND) && .venv/bin/ruff check app tests evals && .venv/bin/ruff format --check app tests evals
	cd $(FRONTEND) && npm run lint

typecheck: ## mypy + tsc
	cd $(BACKEND) && .venv/bin/mypy app
	cd $(FRONTEND) && npm run typecheck

eval: ## Offline grounding evaluation (mock providers)
	cd $(BACKEND) && .venv/bin/python -m evals.run_eval

check: lint typecheck test ## Everything CI should run
