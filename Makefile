.PHONY: setup dev migrate check test-backend test-web test-e2e test-recovery test-load verify

setup:
	cd backend && uv sync --locked --group dev
	cd web && npm ci

dev:
	@echo "db: localhost:5432  api: localhost:8000  web: localhost:5173"
	@echo "stop: Ctrl-C"
	cd backend && PYTHONPATH=src uv run uvicorn x_insight.app:app --port 8000 & cd web && npm run dev & wait

migrate:
	@echo "no migrations defined yet (first migration lands with its feature)"

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
	npx playwright test $(TEST)

test-recovery:
	@echo "no recovery drills yet (first backup lands with its feature)"; exit 1

test-load:
	@echo "no load harness yet (benchmarks land with deployment tuning)"; exit 1

verify: check
	cd backend && uv run pytest tests -q
