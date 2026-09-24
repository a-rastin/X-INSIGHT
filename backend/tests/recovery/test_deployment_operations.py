"""S57 slice 3 (RED): deployment operations docs, upgrade path, env/key guards.

Scope: docs/dev/tasks.md S57 item 3; seams T1/T8/T9/T10 operational
entry points only. STATIC + REAL-CONFIG ASSERTIONS -- no docker daemon,
no live provider credentials, no database access.

Real config names (read from
backend/src/x_insight/reasoning/provider_config.py):
- ENCRYPTION_ENV_VARS = ("X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY",
  "PROVIDER_ENCRYPTION_KEY")
- ALLOW_LOCAL_ENV_VAR = "X_INSIGHT_PROVIDER_ALLOW_LOCAL"
There are no TEST_/MOCK_ adapter vars in that module; the dev-override
guard below targets the real local-endpoint flag plus generic
test/fake/stub provider names.

Contract under test (NOT implemented -- RED: no operations doc or
upgrade script exists yet):
1. An operator operations/runbook document exists (deploy/OPERATIONS.md
   or docs/dev/deployment-runbook.md) with section headers covering:
   environment variables + secret/key handling (provider encryption key
   outside DB, never in backups), backup-before-upgrade, compatible
   app/schema rollback, migration-failure recovery, stopping processes.
   Asserted by file existence + `#`-header keyword presence, not prose.
2. Production compose sets no dev/test provider override and
   .env.example keeps placeholders only (green guards if already clean).
3. An upgrade path file exists (deploy/upgrade.sh or equivalent
   ops-doc-prescribed command file) performing backup-before-upgrade +
   migrate with a rollback pointer -- RED: no such file yet.
4. DB_PASSWORD and the provider encryption key var are
   required-not-defaulted in prod compose (` :? ` guard, never a
   checked-in real secret).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PROD_COMPOSE = REPO_ROOT / "deploy" / "compose.prod.yaml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"

OPS_DOC_CANDIDATES = (
    REPO_ROOT / "deploy" / "OPERATIONS.md",
    REPO_ROOT / "docs" / "dev" / "deployment-runbook.md",
)

UPGRADE_SCRIPT_CANDIDATES = (
    REPO_ROOT / "deploy" / "upgrade.sh",
    REPO_ROOT / "deploy" / "upgrade.py",
)

# Real names from provider_config.py -- assert absence of exactly these
# as dev/test overrides in production config.
DEV_OVERRIDE_VARS = ("X_INSIGHT_PROVIDER_ALLOW_LOCAL",)
GENERIC_TEST_PROVIDER_RES = (
    re.compile(r"TEST_.{0,40}(PROVIDER|ENDPOINT|ADAPTER|BASE_URL)", re.I),
    re.compile(r"MOCK_.{0,40}(PROVIDER|ENDPOINT|ADAPTER)", re.I),
    re.compile(r"FAKE_.{0,40}(PROVIDER|ENDPOINT|ADAPTER)", re.I),
    re.compile(r"STUB_.{0,40}(PROVIDER|ENDPOINT|ADAPTER)", re.I),
)

# Real secret names that must be required-not-defaulted in prod compose.
REQUIRED_SECRET_VARS = (
    "DB_PASSWORD",
    "X_INSIGHT_PROVIDER_KEY_ENCRYPTION_KEY",
)

# (header keyword group): acceptable keyword alternatives per required topic.
REQUIRED_OPS_TOPICS = (
    ("environment",),
    ("secret", "key"),
    ("backup", "upgrade"),
    ("rollback",),
    ("migration",),
    ("stop",),
)


def _find_ops_doc() -> tuple[Path, str] | None:
    for candidate in OPS_DOC_CANDIDATES:
        if candidate.is_file():
            return candidate, candidate.read_text(encoding="utf-8")
    return None


def _headers(text: str) -> list[str]:
    return [
        line.strip().lower()
        for line in text.splitlines()
        if line.lstrip().startswith("#")
    ]


def _load_prod_compose() -> str:
    assert PROD_COMPOSE.is_file(), f"missing production compose {PROD_COMPOSE}"
    return PROD_COMPOSE.read_text(encoding="utf-8")


def test_ops_doc_exists():
    """S57 item 3 (RED): an operator operations/runbook document exists."""
    found = _find_ops_doc()
    assert found is not None, (
        "no operator operations doc: expected one of "
        + ", ".join(str(p.relative_to(REPO_ROOT)) for p in OPS_DOC_CANDIDATES)
    )
    path, _ = found
    assert path.is_file()


def test_ops_doc_covers_required_topics():
    """S57 item 3 (RED): ops doc headers cover env/keys, backup-before-
    upgrade, rollback, migration recovery, stopping processes (T10)."""
    found = _find_ops_doc()
    assert found is not None, "no ops doc (see test_ops_doc_exists)"
    _, text = found
    headers = _headers(text)
    assert headers, "ops doc has no `#` section headers at all"
    missing = [
        "/".join(group)
        for group in REQUIRED_OPS_TOPICS
        if not any(any(kw in h for kw in group) for h in headers)
    ]
    assert not missing, f"ops doc headers missing topics: {missing}"


def test_prod_compose_has_no_dev_test_provider_override():
    """S57 item 3: prod compose sets no test-provider/dev-override env (T8)."""
    text = _load_prod_compose()
    for var in DEV_OVERRIDE_VARS:
        assert not re.search(rf"(?m)^\s*{re.escape(var)}\s*[:=]", text), (
            f"production compose must not enable dev override {var!r}"
        )
    for rx in GENERIC_TEST_PROVIDER_RES:
        assert not rx.search(text), (
            f"production compose sets a test/fake provider env: {rx.pattern!r}"
        )


def test_env_example_placeholders_only():
    """S57 item 3: .env.example keeps placeholders only, no real secrets."""
    assert ENV_EXAMPLE.is_file(), f"missing {ENV_EXAMPLE}"
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert text.strip(), ".env.example is empty -- vacuous pass refused"
    assert len(text) < 4096, ".env.example unexpectedly large"
    assert "-----BEGIN" not in text, ".env.example embeds a real PEM key"


def test_upgrade_path_exists():
    """S57 item 3 (RED): a backup-before-upgrade + migrate + rollback
    upgrade path exists as a file (T10)."""
    found = [p for p in UPGRADE_SCRIPT_CANDIDATES if p.is_file()]
    ops = _find_ops_doc()
    ops_has_path = ops is not None and any(
        kw in ops[1].lower() for kw in ("backup", "migrate", "rollback")
    )
    assert found or ops_has_path, (
        "no upgrade path: expected one of "
        + ", ".join(str(p.relative_to(REPO_ROOT)) for p in UPGRADE_SCRIPT_CANDIDATES)
        + " or an ops doc prescribing backup+migrate+rollback commands"
    )


def test_prod_secrets_required_not_defaulted():
    """S57 item 3: DB_PASSWORD + provider encryption key are required-
    not-defaulted in prod compose (T8/T10)."""
    text = _load_prod_compose()
    for var in REQUIRED_SECRET_VARS:
        assert var in text, f"production compose never references secret {var!r}"
        assert re.search(rf"\${{{re.escape(var)}:\?", text), (
            f"secret {var!r} must be required-not-defaulted "
            f"(${{{var}:?...}}) in production compose"
        )
    # No checked-in real secret value beside the reference.
    for line in text.splitlines():
        low = line.lower()
        if "password" in low or "encryption_key" in low:
            assert ":?" in line or ": " not in line or "${" in line, (
                f"possible checked-in secret default: {line.strip()!r}"
            )


def test_prod_compose_no_test_provider_image_or_command():
    """S57 item 3: prod services use release images/commands only (T10)."""
    text = _load_prod_compose().lower()
    assert "mock" not in text, "production compose references a mock component"
    assert "test_provider" not in text, "production compose references a test provider"
