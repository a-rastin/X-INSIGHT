# X-INSIGHT Progress Tracker

Session: S01 (status: complete)
Outcome and FR/NFR covered: Reproducible dev loop (NFR-01, NFR-05). Failing health test → minimal FastAPI route; minimal React/Vite X-INSIGHT shell; locked installs; Make targets; disposable PostgreSQL dev/test DBs.
Files/migrations/content versions changed: backend/src/x_insight/app.py (health route); web/{package.json,package-lock.json,index.html,vite.config.ts,tsconfig.json,src/main.tsx,src/app/App.tsx,Dockerfile}; backend/Dockerfile; compose.yaml; Makefile; .env.example; .github/workflows/ci.yml. No migrations, no clinical content.
Approved seams exercised: T1/T9 smoke only (health endpoint via TestClient + real HTTP; shell via served page).
Red evidence: backend/tests/http/test_health.py → 404 on GET /api/v1/health before route existed.
Green evidence: make verify → ruff/mypy/tsc/vite build pass, 1 passed. Real-HTTP smoke: uvicorn → {"status":"ok"}; vite preview → page contains X-INSIGHT. Runtimes: Python 3.11.16, Node 22.23.2, PostgreSQL 14.24, React 19.1.1, Vite 7.1.7, fastapi 0.141.1, pgmpy 1.1.2, mcp (import ok).
Review/limitations/unrun checks: test-web/test-e2e/test-recovery/test-load correctly report "no suite yet" (exit 1). compose services not runtime-tested (no docker daemon). Ports: db 5432, api 8000, web 5173. Stop: Ctrl-C (make dev) / drop xinsight_dev|xinsight_test DBs. No credentials in tracked files (only local-dev placeholder password).
Content approvals: n/a (no content).
Remaining work and next eligible session: S02 (real database wiring/migrations per tasks.md).

Session: S02 (status: complete)
Outcome and FR/NFR covered: Real persistence + request contracts (NFR-04–05, cross-cutting FR-42). Liveness stays DB-free; readiness reports ready/unavailable/incompatible-schema; request correlation + standard error envelope without tracebacks; 1 MiB body limit + structured 422 field errors; one shared transaction context with transaction-scoped audit insert; canonical JSON/hash + UTC helpers documented at future uses.
Files/migrations/content versions changed: backend/src/x_insight/{__init__.py,db.py,contracts.py,app.py,operations/__init__.py,operations/audit.py}; backend/{alembic.ini,migrations/env.py,migrations/versions/0001_init.py} (revision 0001: audit_events); backend/tests/{conftest.py,http/test_contracts.py}; Makefile (migrate runs alembic upgrade head); backend/{pyproject.toml,uv.lock} (sqlalchemy==2.0.54, alembic==1.20.0). No clinical content.
Approved seams exercised: T1 (HTTP via TestClient + real uvicorn smoke).
Red evidence: backend/tests/http/test_contracts.py → 404 on GET /api/v1/ready before route existed (3 failed); later ImportError for register_exception_handlers before handler-registration refactor.
Green evidence: 9 passed (test_contracts 8 + test_health 1); make check (ruff/mypy/tsc/vite build) pass; make migrate on fresh scratch DB → 0001 then readiness ok; real-HTTP smoke: fresh DB /ready 200 {"status":"ready"}; bad-URL server /ready 503 UNAVAILABLE envelope with matching x-request-id, no DSN/traceback. Disposable script verified audit rollback/commit + canonical/hash/UTC/If-Match/Idempotency-Key parsing (rows cleaned up, not committed as tests). Runtimes: Python 3.11.16, PostgreSQL 14.24, sqlalchemy 2.0.54, alembic 1.20.0.
Review/limitations/unrun checks: Logical DB roles only (app/migration/readonly env vars fall back to one local role; no CREATE ROLE SQL until privilege-sensitive domain tables land in S03/S06). 422 handler proven via test-local route reusing production registration (no test-only production endpoint). Audit/canonical helpers verified disposably; first HTTP-level audit behavior lands with S03 mutations. Size limit enforces Content-Length only (chunked edge noted). compose not runtime-tested. test-web/test-e2e/test-recovery/test-load still correctly report no suite yet.
Content approvals: n/a (synthetic probe strings only, never released).
Remaining work and next eligible session: S03 (login/sessions/own credentials, first audit-covered mutations) and S15 (DDI parse) are eligible; S03 uses db.transaction + record_audit + If-Match/Idempotency-Key helpers from this session.
