"""S57 slice 1 (RED): pinned production images + Compose topology.

Scope: docs/dev/tasks.md S57 item 1; seams T1/T8/T9/T10 operational
entry points only. STATIC FILE ASSERTIONS -- no docker daemon, no live
provider credentials, no database access.

Production contract under test (NOT implemented -- RED: no production
Compose file exists yet):
- Production Compose file (deploy/compose.prod.yaml, or compose.yaml
  carrying a production profile) defines exactly the services
  edge, app (or api), worker, db.
- db persists a named volume and exposes NO host ports.
- No MCP service/ports are published publicly; the worker spawns the
  private MCP (worker block references x_insight.mcp_server/mcp_host).
- Every production image is pinned by digest or exact version
  (no :latest, no untagged, no build-only service); Dockerfiles pin
  their base images the same way.
- The browser client (web/src/app/api.ts) uses only relative /api/v1
  routes in fetch calls (no absolute http:// or localhost:8000).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PROD_COMPOSE_CANDIDATES = (
    REPO_ROOT / "deploy" / "compose.prod.yaml",
    REPO_ROOT / "deploy" / "compose.prod.yml",
)
DEV_COMPOSE = REPO_ROOT / "compose.yaml"
API_TS = REPO_ROOT / "web" / "src" / "app" / "api.ts"
BACKEND_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
WEB_DOCKERFILE = REPO_ROOT / "web" / "Dockerfile"

SERVICE_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$", re.M)
IMAGE_RE = re.compile(r"image:\s*([\"']?)(\S+)\1")

EXPECTED_TOPOLOGIES = (
    {"edge", "app", "worker", "db"},
    {"edge", "api", "worker", "db"},
)


def _service_names(compose_text: str) -> list[str]:
    services_block = compose_text.split("\nvolumes:", 1)[0]
    return SERVICE_RE.findall(services_block.split("\nservices:", 1)[-1])


def _service_block(compose_text: str, name: str) -> str:
    pattern = re.compile(rf"^  {re.escape(name)}:\s*$", re.M)
    match = pattern.search(compose_text)
    assert match, f"service {name!r} not found in production Compose file"
    rest = compose_text[match.end() :]
    nxt = SERVICE_RE.search(rest)
    top = re.search(r"(?m)^[A-Za-z0-9_-]+:\s*$", rest)
    cuts = [m.start() for m in (nxt, top) if m]
    return rest[: min(cuts)] if cuts else rest


def _load_prod_compose() -> tuple[Path, str]:
    for candidate in PROD_COMPOSE_CANDIDATES:
        if candidate.is_file():
            return candidate, candidate.read_text(encoding="utf-8")
    if DEV_COMPOSE.is_file():
        text = DEV_COMPOSE.read_text(encoding="utf-8")
        if set(_service_names(text)) in EXPECTED_TOPOLOGIES:
            return DEV_COMPOSE, text
    pytest.fail(
        "no production Compose topology: expected deploy/compose.prod.yaml "
        "(or a compose.yaml production profile) defining exactly "
        "services edge, app (or api), worker, db"
    )


def _assert_image_pinned(ref: str, where: str) -> None:
    assert "latest" not in ref.lower(), f"{where}: unpinned :latest image {ref!r}"
    assert "@sha256:" in ref or ":" in ref, (
        f"{where}: untagged image {ref!r} (implicit :latest)"
    )


def test_prod_compose_file_exists():
    """S57 item 1 (RED): a production Compose file defines the topology."""
    path, _ = _load_prod_compose()
    assert path.is_file()


def test_prod_services_topology():
    """S57 item 1 (RED): exactly edge, app (or api), worker, db (T8/T10)."""
    _, text = _load_prod_compose()
    assert set(_service_names(text)) in EXPECTED_TOPOLOGIES, (
        f"production services must be exactly edge/app-or-api/worker/db, "
        f"got {sorted(_service_names(text))}"
    )


def test_prod_db_persisted_volume_no_host_ports():
    """S57 item 1 (RED): db persists a named volume, publishes no ports."""
    _, text = _load_prod_compose()
    db_block = _service_block(text, "db")
    assert re.search(r"(?m)^\s+volumes:\s*$", db_block), "db has no volumes"
    mount = re.search(r"([\w-]+):/var/lib/postgresql/data", db_block)
    assert mount, "db has no persisted named-volume mount for pgdata"
    assert re.search(r"(?m)^volumes:\s*$", text), "no top-level volumes section"
    assert re.search(rf"(?m)^  {re.escape(mount.group(1))}:", text), (
        f"db volume {mount.group(1)!r} is not a declared named volume"
    )
    assert not re.search(r"(?m)^\s+ports:\s*$", db_block), (
        "db must expose NO host ports in production"
    )


def test_prod_no_public_mcp_ports():
    """S57 item 1 (RED): no MCP service or published MCP ports (T9/T10)."""
    path, text = _load_prod_compose()
    names = _service_names(text)
    assert "mcp" not in names, f"{path.name} must not publish an mcp service"
    for name in names:
        block = _service_block(text, name)
        if re.search(r"(?m)^\s+ports:\s*$", block):
            assert "mcp" not in block.lower(), (
                f"service {name!r} publishes MCP-related ports"
            )


def test_prod_worker_spawns_private_mcp():
    """S57 item 1 (RED): worker spawns the private MCP (T9/T10)."""
    _, text = _load_prod_compose()
    worker = "worker" if "worker" in _service_names(text) else "app"
    block = _service_block(text, worker)
    assert "x_insight.mcp_server" in block or "mcp_host" in block, (
        "worker service must spawn the private MCP "
        "(x_insight.mcp_server or mcp_host reference)"
    )
    assert not re.search(r"(?m)^\s+ports:\s*$", block), (
        "worker/MCP must stay private (no published ports)"
    )


def test_prod_images_pinned():
    """S57 item 1 (RED): every production image pinned, no :latest (T10)."""
    _, text = _load_prod_compose()
    for name in _service_names(text):
        block = _service_block(text, name)
        found = IMAGE_RE.findall(block)
        assert found, f"service {name!r} has no pinned image (build-only?)"
        for _, ref in found:
            _assert_image_pinned(ref, f"service {name!r}")


def test_prod_dockerfiles_pinned():
    """S57 item 1: Dockerfiles pin base images (no :latest)."""
    for dockerfile in (BACKEND_DOCKERFILE, WEB_DOCKERFILE):
        assert dockerfile.is_file(), f"missing {dockerfile}"
        for line in dockerfile.read_text(encoding="utf-8").splitlines():
            if line.startswith("FROM "):
                _assert_image_pinned(line.split(maxsplit=1)[1], str(dockerfile))


def test_prod_edge_config_present():
    """S57 item 1 (RED): the edge service has a checked-in edge config."""
    _, text = _load_prod_compose()
    edge_block = _service_block(text, "edge").lower()
    deploy_files = " ".join(p.name for p in (REPO_ROOT / "deploy").glob("*")).lower()
    assert (
        "nginx" in edge_block
        or "caddy" in edge_block
        or "configs:" in edge_block
        or "edge" in deploy_files
        or "nginx" in deploy_files
        or "caddy" in deploy_files
    ), "no edge config: edge service references none and deploy/ holds none"


def test_prod_browser_uses_relative_routes():
    """S57 item 1: browser fetch calls use relative /api/v1 routes (T1)."""
    assert API_TS.is_file(), f"missing browser client {API_TS}"
    lines = API_TS.read_text(encoding="utf-8").splitlines()
    fetch_lines = [
        line
        for line in lines
        if "fetch(" in line and line.strip()[:2] not in ("//", "*")
    ]
    assert fetch_lines, "no fetch calls found -- vacuous pass refused"
    assert any(
        '"/api/v1' in line or "'/api/v1" in line or "`/api/v1" in line
        for line in fetch_lines
    ), "browser client makes no relative /api/v1 fetch calls"
    for line in fetch_lines:
        assert "http://" not in line, f"absolute http:// URL in api.ts: {line}"
        assert "https://" not in line or "/api/v1" in line, (
            f"absolute URL in api.ts fetch call: {line}"
        )
        assert "localhost" not in line and "127.0.0.1" not in line, (
            f"localhost-bound URL in api.ts fetch call: {line}"
        )
