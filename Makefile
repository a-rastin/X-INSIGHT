.PHONY: setup dev migrate check test-backend test-web test-e2e test-recovery test-load verify

setup:
	cd backend && uv sync --locked --group dev
	cd web && npm ci

dev:
	@echo "db: localhost:5432  api: localhost:8000  web: localhost:5173"
	@echo "stop: Ctrl-C"
	cd backend && PYTHONPATH=src uv run uvicorn x_insight.app:app --port 8000 & cd web && npm run dev & wait

migrate:
	cd backend && uv run alembic upgrade head

check:
	cd backend && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy src
	cd web && npm run check && npm run build

test-backend:
	cd backend && uv run pytest $(if $(TEST),$(TEST),tests) -q

test-web:
	@test -d web/tests || (echo "no web suite yet (first browser behavior lands with its feature)"; exit 1)
	cd web && npm test -- $(TEST)

test-e2e:
	@test -d e2e || (echo "no e2e journeys yet (first journey lands with its feature)"; exit 1)
	NODE_PATH=$(CURDIR)/web/node_modules ./web/node_modules/.bin/playwright test $(TEST)

test-recovery:
	cd backend && uv run pytest tests/recovery -q

test-load:
	cd backend && PYTHONPATH=src uv run python -m x_insight.load --patients $${X_INSIGHT_LOAD_PATIENTS:-50} --threads $${X_INSIGHT_LOAD_THREADS:-4} --dataset $${X_INSIGHT_LOAD_DATASET:-synthetic-ci-default} --host $${X_INSIGHT_LOAD_HOST:-ci}

verify: check
	cd backend && uv run pytest tests -q
