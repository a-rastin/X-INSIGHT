"""S58 item 1: synthetic load harness over public HTTP (seams T1/T8).

Scope: plan.md S58 item 1 / plan.md section 11 planning load. This slice
uses T1 only: synthetic patients are created through public POST /patients
and ordinary saves/searches/polls run concurrently through public routes
against real PostgreSQL. No new seam, no live provider calls (the provider
section of the report stays zero/null), no real patient data, no new DB
tables. Synthetic names are letters-only NFC; synthetic IDs are ten ASCII
digits unique per run; draft markers carry no clinical content.
"""

from __future__ import annotations

import concurrent.futures
import math
import random
import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

LOAD_PHYSICIAN_USERNAME = "loadharness"
LOAD_PHYSICIAN_PASSWORD = "synthetic-load-password-one"

_SYNTHETIC_FIRST_NAME = "Loadtest"
_SYNTHETIC_LAST_NAME_STEM = "Synthetic"
_SYNTHETIC_SEARCH_QUERY = "Loadtest"


def _p95(values: list[float]) -> float:
    """95th percentile (nearest-rank); 0.0 when nothing was measured."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return float(ordered[index])


def _letter_suffix(index: int) -> str:
    """Bijective base-26 letters-only suffix: 0->A, 25->Z, 26->AA."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    suffix = ""
    value = index
    while True:
        suffix = alphabet[value % 26] + suffix
        value = value // 26 - 1
        if value < 0:
            return suffix


def _synthetic_patient_body(index: int, patient_id: str) -> dict[str, Any]:
    """Clearly synthetic demographics; letters-only NFC names, no clinic."""
    return {
        "first_name": _SYNTHETIC_FIRST_NAME,
        "last_name": f"{_SYNTHETIC_LAST_NAME_STEM}{_letter_suffix(index)}",
        "sex": "F" if index % 2 else "M",
        "age": 30,
        "patient_id": patient_id,
        "clinical_status": "first_time",
    }


def _synthetic_ids(patient_count: int) -> list[str]:
    """Ten ASCII digits each: one random prefix per run + padded index."""
    if patient_count < 1:
        raise ValueError("patient_count must be >= 1")
    width = max(1, len(str(patient_count - 1)))
    prefix_width = 10 - width
    prefix = random.randint(0, 10**prefix_width - 1)
    stem = f"{prefix:0{prefix_width}d}"
    return [f"{stem}{index:0{width}d}" for index in range(patient_count)]


def _default_client_factory() -> TestClient:
    """Public-HTTP client for the measured app (lazy: cheap module import)."""
    from x_insight.app import app  # noqa: PLC0415

    return TestClient(app)


def _login(client: TestClient, username: str, password: str, role: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password, "role": role},
    )
    if response.status_code != 200:
        raise RuntimeError(f"load login failed for {username}: {response.status_code}")


def _csrf(client: TestClient) -> str:
    token = client.cookies.get("xinsight_csrf")
    if not token:
        raise RuntimeError("load client is missing its CSRF cookie")
    return token


def _ensure_physician(admin: TestClient, run_token: str) -> None:
    """Create the synthetic load physician; tolerate reruns (409)."""
    response = admin.post(
        "/api/v1/physicians",
        json={
            "username": LOAD_PHYSICIAN_USERNAME,
            "password": LOAD_PHYSICIAN_PASSWORD,
        },
        headers={
            "X-CSRF-Token": _csrf(admin),
            "Idempotency-Key": f"load-{run_token}",
        },
    )
    if response.status_code not in (201, 409):
        raise RuntimeError(
            f"load physician setup failed: {response.status_code} {response.text[:200]}"
        )


def run(
    *,
    host: str,
    dataset: str,
    duration_s: float = 5.0,
    patient_count: int = 5,
    concurrency: int = 2,
    client_factory: Callable[[], TestClient] | None = None,
) -> dict[str, Any]:
    """Run a tiny synthetic load and report host/dataset/duration/p95.

    ``duration_s`` is accepted for contract compatibility (intended budget
    label); the report carries the measured wall time. ``client_factory``
    injects the public-HTTP client (tests use TestClient); the measured
    dataset is always created via public POST /patients, never direct SQL.
    Provider work is never issued: ``provider_calls`` is 0 and
    ``provider_p95_s`` is None.
    """
    if patient_count < 1:
        raise ValueError("patient_count must be >= 1")
    workers = max(1, int(concurrency))
    factory: Callable[[], TestClient] = client_factory or _default_client_factory
    run_token = f"{random.randint(0, 999999):06d}"
    started = time.monotonic()

    setup = factory()
    try:
        _login(setup, "admin", "admin", "admin")
        _ensure_physician(setup, run_token)
        _login(
            setup,
            LOAD_PHYSICIAN_USERNAME,
            LOAD_PHYSICIAN_PASSWORD,
            "physician",
        )
        physician_csrf = _csrf(setup)
        created: list[dict[str, str]] = []
        for index, synthetic_id in enumerate(_synthetic_ids(patient_count)):
            response = setup.post(
                "/api/v1/patients",
                json=_synthetic_patient_body(index, synthetic_id),
                headers={
                    "X-CSRF-Token": physician_csrf,
                    "Idempotency-Key": f"load-{run_token}-{index}",
                },
            )
            if response.status_code != 201:
                raise RuntimeError(
                    f"load patient creation failed: {response.status_code} "
                    f"{response.text[:200]}"
                )
            payload = response.json()
            encounter = payload["encounter"]
            created.append(
                {
                    "encounter_id": str(encounter["id"]),
                    "revision": str(encounter["revision"]),
                }
            )
    finally:
        setup.close()

    clients: dict[int, TestClient] = {}
    clients_lock = threading.Lock()

    def thread_client() -> TestClient:
        ident = threading.get_ident()
        with clients_lock:
            existing = clients.get(ident)
            if existing is None:
                existing = factory()
                _login(
                    existing,
                    LOAD_PHYSICIAN_USERNAME,
                    LOAD_PHYSICIAN_PASSWORD,
                    "physician",
                )
                clients[ident] = existing
            return existing

    def do_save(target: dict[str, str]) -> float:
        client = thread_client()
        begin = time.monotonic()
        response = client.patch(
            f"/api/v1/encounters/{target['encounter_id']}",
            json={"draft_data": {"synthetic_load_marker": "synthetic"}},
            headers={
                "X-CSRF-Token": _csrf(client),
                "If-Match": target["revision"],
            },
        )
        elapsed = time.monotonic() - begin
        if response.status_code != 200:
            raise RuntimeError(
                f"load save failed: {response.status_code} {response.text[:200]}"
            )
        return elapsed

    def do_search() -> float:
        client = thread_client()
        begin = time.monotonic()
        response = client.get(
            "/api/v1/patients",
            params={"q": _SYNTHETIC_SEARCH_QUERY, "limit": 25},
        )
        elapsed = time.monotonic() - begin
        if response.status_code != 200:
            raise RuntimeError(
                f"load search failed: {response.status_code} {response.text[:200]}"
            )
        return elapsed

    def do_poll() -> float:
        client = thread_client()
        begin = time.monotonic()
        response = client.get("/api/v1/ready")
        elapsed = time.monotonic() - begin
        if response.status_code != 200:
            raise RuntimeError(
                f"load poll failed: {response.status_code} {response.text[:200]}"
            )
        return elapsed

    saves: list[float] = []
    searches: list[float] = []
    polls: list[float] = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            save_futures = [pool.submit(do_save, target) for target in created]
            search_futures = [pool.submit(do_search) for _ in range(patient_count)]
            poll_futures = [pool.submit(do_poll) for _ in range(patient_count)]
            for future in save_futures:
                saves.append(future.result())
            for future in search_futures:
                searches.append(future.result())
            for future in poll_futures:
                polls.append(future.result())
    finally:
        for thread_owned in clients.values():
            thread_owned.close()

    ordinary = saves + searches + polls
    return {
        "host": host,
        "dataset": dataset,
        "duration_s": time.monotonic() - started,
        "patient_count": patient_count,
        "counts": {
            "patients_created": len(created),
            "saves": len(saves),
            "searches": len(searches),
            "polls": len(polls),
        },
        "saves_p95_s": _p95(saves),
        "searches_p95_s": _p95(searches),
        "polls_p95_s": _p95(polls),
        "ordinary_p95_s": _p95(ordinary),
        "provider_calls": 0,
        "provider_p95_s": None,
    }
