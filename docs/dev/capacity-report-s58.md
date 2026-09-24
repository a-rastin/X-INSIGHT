# X-INSIGHT capacity report — S58 (measured 2026-09-24)

Scope: tasks.md S58 items 1–4; plan.md §11. Every number below comes from
an executed command pasted in this file. Nothing is invented. Synthetic
inputs only (`Loadtest Synthetic*`, random ten-digit IDs, `synthetic_*`
markers); no live provider calls; no real patient data. Provider latency
is reported separately from ordinary requests throughout.

Status of the four slices at report time: all green, uncommitted
(`metrics.py` + `GET /api/v1/ops-metrics`, `load/` + `make test-load`,
`models/capacity.py`, `models/definition_cache.py` wired into
`ddi/terminology.py`, `e2e/ops-status.spec.ts` green per slice handoff).

## 1. Environment

Host (this machine, not a docker/production host):

```text
$ uname -a
Linux A 5.15.0-191-generic #201-Ubuntu SMP Fri Aug 7 18:39:04 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

```text
Mem: 31Gi total, 27Gi available; 8 vCPU (nproc); / 469G, 8% used
psql (PostgreSQL) 14.24 (Ubuntu 14.24-0ubuntu0.22.04.1)
backend runtime: Python 3.11.16 (uv), pgmpy 1.1.2, float64, artifact-node-order
```

Report date (UTC): 2026-09-24T01:34:29Z. Load runs below executed against
the disposable **dev** database via public HTTP (TestClient against the
real app + real PostgreSQL), not a production/compose host.

## 2. Load runs — `make test-load` (S58 item 1)

### 2a. CI default: 50 synthetic patients

```text
$ make test-load
cd backend && PYTHONPATH=src uv run python -m x_insight.load --patients ${X_INSIGHT_LOAD_PATIENTS:-50} --threads ${X_INSIGHT_LOAD_THREADS:-4} --dataset ${X_INSIGHT_LOAD_DATASET:-synthetic-ci-default} --host ${X_INSIGHT_LOAD_HOST:-ci}
{
  "counts": {
    "patients_created": 50,
    "polls": 50,
    "saves": 50,
    "searches": 50
  },
  "dataset": "synthetic-ci-default",
  "duration_s": 4.64834764302941,
  "host": "ci",
  "ordinary_p95_s": 0.0128874690271914,
  "patient_count": 50,
  "polls_p95_s": 0.011722873954568058,
  "provider_calls": 0,
  "provider_p95_s": null,
  "saves_p95_s": 0.01748696295544505,
  "searches_p95_s": 0.010137190984096378
}
```

Reading: 50 patients created via public `POST /patients`, then 50
acknowledged saves + 50 directory searches + 50 readiness polls run
concurrently (4 threads). Wall 4.65 s. Ordinary p95 0.0129 s (saves p95
0.0175 s, searches p95 0.0101 s, polls p95 0.0117 s). Provider section is
honestly zero/null — the harness never issues provider work.

### 2b. Scale run: 1000 synthetic patients (largest feasible in time box)

```text
$ X_INSIGHT_LOAD_PATIENTS=1000 X_INSIGHT_LOAD_THREADS=8 X_INSIGHT_LOAD_DATASET=synthetic-scale-1000 make test-load
cd backend && PYTHONPATH=src uv run python -m x_insight.load --patients ${X_INSIGHT_LOAD_PATIENTS:-50} --threads ${X_INSIGHT_LOAD_THREADS:-4} --dataset ${X_INSIGHT_LOAD_DATASET:-synthetic-ci-default} --host ${X_INSIGHT_LOAD_HOST:-ci}
{
  "counts": {
    "patients_created": 1000,
    "polls": 1000,
    "searches": 1000,
    "saves": 1000
  },
  "dataset": "synthetic-scale-1000",
  "duration_s": 79.19022721104557,
  "host": "ci",
  "ordinary_p95_s": 0.0288633510353975,
  "patient_count": 1000,
  "polls_p95_s": 0.023858238011598587,
  "provider_calls": 0,
  "provider_p95_s": null,
  "saves_p95_s": 0.03306718001840636,
  "searches_p95_s": 0.025516972003970295
}
```

Reading: 1000 patients + 3000 concurrent ordinary operations (8 threads).
Wall 79.19 s. Ordinary p95 0.0289 s (saves p95 0.0331 s, searches p95
0.0255 s, polls p95 0.0239 s). Both runs clear the provisional ordinary
p95 < 1 s target with >30× headroom **on this host against the dev DB** —
not a production-host claim.

### 2c. Full 10,000 — NOT run (remaining, exact resume command)

The §11 planning load (10,000 synthetic patients) was not executed: at
the measured ~79 s per 1000 patients this needs ~13 minutes plus cleanup,
outside this session's time box, and there is no docker/production host
to measure against yet. Resume command (run from repository root):

```sh
X_INSIGHT_LOAD_PATIENTS=10000 X_INSIGHT_LOAD_THREADS=4 \
  X_INSIGHT_LOAD_DATASET=synthetic-planning-10k make test-load
```

Record host (`uname -a`), dataset, `duration_s`, and all `*_p95_s` when it
runs; append them here. Linear extrapolation from §2b suggests ~800 s wall
with ordinary p95 still far below 1 s, but extrapolation is not a result.

## 3. Model structure + synthetic inference bench (S58 item 2)

Clinical CPT values cannot be estimated without the provider path, so no
provider numbers are reported here. What was measured: (a) structure of
every shipped draft `content/questions/*/network.xml` via
`models/semantics.check_admission` (xml bytes, node count, CPT cells);
(b) inference timing + request/output bytes via
`models/capacity.measure` on a synthetic 2-node equivalent (hand-checked
posterior 0.22), labeled as such.

### 3a. Draft network structures (all 12 present packages)

```text
$ PYTHONPATH=src uv run python -c "…validate_xmlbif + check_admission + check_semantics…"
acute_dystonia         xml_bytes=16515 nodes=13 cells=836  admitted=True executable=True errs=[]
aggression_clozapine   xml_bytes=17564 nodes=14 cells=213  admitted=True executable=True errs=[]
akathisia              xml_bytes=9981  nodes=9  cells=184  admitted=True executable=True errs=[]
continue_or_adjust     xml_bytes=12608 nodes=12 cells=141  admitted=True executable=True errs=[]
established_case_clozapine xml_bytes=15234 nodes=18 cells=309 admitted=True executable=True errs=[]
high_suicide_clozapine xml_bytes=11356 nodes=14 cells=213  admitted=True executable=True errs=[]
hospitalization        xml_bytes=5281  nodes=5  cells=337  admitted=True executable=True errs=[]
lai_indication_choice  xml_bytes=15393 nodes=14 cells=574  admitted=True executable=True errs=[]
no_improvement_clozapine xml_bytes=6954 nodes=7 cells=71   admitted=True executable=True errs=[]
parkinsonism           xml_bytes=19992 nodes=20 cells=795  admitted=True executable=True errs=[]
pharmacotherapy        xml_bytes=19135 nodes=5  cells=2389 admitted=True executable=True errs=[]
tardive_dyskinesia     xml_bytes=8650  nodes=9  cells=242  admitted=True executable=True errs=[]
```

File hashes (sha256, first 16 hex; bytes on disk 2026-09-22):

```text
acute_dystonia 16515 6f0e70d6293c2baf | aggression_clozapine 17564 59ee680ad96a3608
akathisia 9981 35e2db6b91f7fe0f | continue_or_adjust 12608 329632da1fcba4df
established_case_clozapine 15234 8f5c8ec20f0e0997 | high_suicide_clozapine 11356 53923f50991636ea
hospitalization 5281 c586be50178cd7ed | lai_indication_choice 15393 c1c78c33003aa7e3
no_improvement_clozapine 6954 9a37a5a9bfcbcbd5 | parkinsonism 19992 25b019064ced63a5
pharmacotherapy 19135 e8491d5e225c56d0 | tardive_dyskinesia 8650 2d573727c1c332ad
```

Notes: only 12 packages ship a `network.xml` — `involuntary_care` (R3)
has no draft package (blocked on jurisdiction criteria per tasks.md S28),
so 13-question coverage is structurally incomplete regardless of these
numbers. All 12 validate XSD, admit under `DEFAULT_LIMITS`
(`max_xml_bytes` 262144, `max_nodes` 64, `max_cpt_cells` 10000), and are
semantically executable **as structures** — the shipped CPT placeholders
are draft content, not provider-estimated all-CPT tables, and `executable`
here means valid dimensions/normalization/ordering, never clinical
validity. Largest structure: parkinsonism (19992 bytes / 20 nodes / 795
cells); largest table mass: pharmacotherapy (2389 cells on 5 nodes).
Admission limits retain ≥10× headroom over every measured structure
(262144/19992 ≈ 13× bytes, 64/20 ≈ 3× nodes, 10000/2389 ≈ 4× cells).

### 3b. Synthetic inference bench (timing + sizes, NOT clinical)

Single-sample probe, synthetic 2-node network (A root [80,20];
B|A=no [90,10], B|A=yes [30,70]; query P(B=yes) = 0.22 by hand
arithmetic), exact inference via pinned engine:

```text
ENGINE_PIN={"dtype": "float64", "elimination_order": "artifact-node-order",
  "engine": "pgmpy.VariableElimination", "engine_version": "1.1.2", "python": "3.11.16"}
{
 "admitted": true,
 "failure_kind": "ok",
 "inference_wall_s": 0.001654537976719439,
 "output_bytes": 376,
 "peak_rss_delta_bytes": 0,
 "posterior": 0.22,
 "request_bytes": 425
}
measurements={"cpt_cells": 6, "inference_wall_s": 0.001654537976719439,
  "node_count": 2, "output_bytes": 376, "peak_rss_delta_bytes": 0,
  "request_bytes": 425, "xml_bytes": 376}
limits={"max_cpt_cells": 10000, "max_nodes": 64, "max_xml_bytes": 262144}
diagnostics=["cpt_cells=6 <= 10000", "dtype=float64",
  "elimination_order=artifact-node-order", "engine=pgmpy.VariableElimination:1.1.2",
  "node_count=2 <= 64", "output_bytes=376", "posterior_computed=true",
  "request_bytes=425", "xml_bytes=376 <= 262144"]
```

Reading: complete CPT request 425 B, effective-XML output 376 B, exact
posterior 0.22 (matches hand arithmetic to 1e-9 in the committed test),
wall ~1.65 ms, RSS delta 0 (below existing process peak — the documented
`ru_maxrss` granularity limitation, not zero memory use). Failure paths
are covered by the committed suite, not re-pasted here: over-limit input
returns `rejected` with diagnostics and no posterior; impossible evidence
and zero timeout fail loudly with bounded (≤500-char) errors. No
clinical-table timing is claimed: a 20-node/2389-cell clinical-shaped
timing run awaits real estimated CPTs and is listed under misses.

## 4. Operational metrics sample (S58 item 3)

Admin `GET /api/v1/ops-metrics` against the dev DB (real state, including
a `succeeded` backup row from earlier recovery work on this host):

```text
$ PYTHONPATH=src uv run python -c "…TestClient login + GET /api/v1/ops-metrics…"
login 200
metrics 200
{
 "alerts": {"disk_high": false, "missing_heartbeat": true,
  "provider_auth_failure": false, "queue_age_exceeded": false},
 "backup": {"last_success_at": "2026-09-23T23:43:30.566385Z", "status": "succeeded"},
 "disk": {"path": "/root/X-INSIGHT/backend/var/backups", "usage_percent": 7.106210920005052},
 "heartbeat": {"last_heartbeat_age_seconds": null, "missing": true},
 "inference": {"limit_rejections": 0},
 "provider": {"auth_failures": 0, "retries": 0},
 "queue": {"oldest_eligible_age_seconds": null},
 "saves": {"failures": 0},
 "schema_version": 1
}
cache-control: private, no-store
```

Alert evaluation on this sample: `missing_heartbeat: true` is the honest
cold state (no worker heartbeats ever recorded on this dev DB) with an
empty queue and zero provider failures — expected on idle, not an
incident. `queue_age_exceeded: false` (null age), `provider_auth_failure:
false` (0 < 2), `disk_high: false` (7.1% < 80%). Role enforcement
(physician 403, anonymous 401) and the no-secrets/no-clinical-payload
shape are asserted by `tests/http/test_ops_metrics.py` (3 passed, §6).
`saves.failures: 0` is the documented honest zero — no save-failure
ledger exists yet (S47 counters pending), so this field currently cannot
go nonzero; do not read it as proof of zero failures.

## 5. Concurrency, fairness, saturation, caches (S58 item 4)

From `tests/worker/test_capacity_concurrency.py` (3 passed, real
PostgreSQL + deterministic queue clock, §6):

- **Two-slot global concurrency + saturation 429**: three eligible jobs
  (one physician, three encounters, synthetic single-question bundle);
  two `claim_next_job()` calls claim, the third returns `None` (both
  provider slots live); the unclaimed run still reads 200 with one
  `queued` job. With admission capped at 3 live runs, a fourth run
  creation returns **429** with the standard error envelope and nothing
  is deleted (queued run + fresh draft both re-readable).
- **Fair progress**: physicians A (runs A1, A2) and B (run B1) queued;
  sequential `run_once()` claims exactly 2 (third reports busy); the
  served set is {A, B} — rotation defeats pure-FIFO starvation — and the
  served A job is the oldest (A1), preserving within-physician FIFO.
- **Bounded caches, no patient reuse**: `definition_cache` with
  `MAX_ENTRIES = 128` — same content hash parses once; filling past the
  bound evicts (live size ≤ 128) and an evicted hash re-parses on next
  use. Two patients against the same synthetic bundle get distinct run
  ids with one job each scoped to its own run; run reads are
  `private, no-store`. Production wiring: `ddi/terminology.py`
  `load_terminology` parses immutable catalog bytes once per
  `sha256:TERMINOLOGY_VERSION` key through this LRU; patient data never
  flows through it.

No broker, Redis, or database cache table was added — per plan.md §11,
none is authorized without measured contention evidence, and none was
measured here.

## 6. Scoped verification (this session)

```text
$ uv run ruff check src/x_insight/operations/metrics.py src/x_insight/load/ \
    src/x_insight/models/capacity.py src/x_insight/models/definition_cache.py \
    src/x_insight/ddi/terminology.py src/x_insight/operations/routes.py
All checks passed!
$ uv run ruff format --check […same files + 4 test files…]
12 files already formatted
$ uv run mypy [same 6 source paths]
…only 4 pre-existing S04 identity/accounts.py RowMapping arg-type errors
 (accounts.py:303,350,403,479 — untouched, not from this work)…
$ uv run pytest tests/http/test_ops_metrics.py -q        → 3 passed (1.52s)
$ uv run pytest tests/load/test_load.py -q               → 3 passed (2.84s)
$ uv run pytest tests/models/test_capacity.py -q         → 3 passed (1.13s)
$ uv run pytest tests/worker/test_capacity_concurrency.py -q → 3 passed (3.27s)
```

Each suite ran sequentially (parallel backend suites deadlock on
TRUNCATE). Runtimes: Python 3.11.16, PostgreSQL 14.24, pytest 9.1.1.
Unrun: `e2e/ops-status.spec.ts` was green per slice handoff but not
re-run in this session; full `make check` (web build) and full backend
suite were out of scope and not run.

## 7. Provisional-target verdict (not an SLA)

- Ordinary p95 < 1 s at planning load: **on track on this host** — CI 50
  p95 0.0129 s, scale-1000 p95 0.0289 s — but the 10k planning load and
  any production-like host are unmeasured, so **no SLA is claimed**.
- Provider latency: separate by construction (harness reports
  `provider_calls: 0`, `provider_p95_s: null`); live-provider behavior is
  explicitly unmeasured.
- Restore drill < 30 min: untouched by this session; see recovery
  runbook Sessions S54–S56.

## 8. Explicit misses and remediation tasks

1. **Full 10k planning load not run.** Remediation: run the resume
   command in §2c on a compose/production-like host, append
   host/dataset/duration/p95 here. Owner: next capacity session.
2. **No docker/production host measured.** All timings are dev-DB on a
   31 GiB/8-vCPU workstation. Remediation: repeat §2a–§2c after S57
   install on the reference 2 vCPU/4 GB RAM/20 GB host.
3. **`involuntary_care` (R3) has no draft package** — 12/13 networks
   measured. Remediation: S28 drafting + owner jurisdiction decision.
4. **No clinical-shaped inference timing.** The bench in §3b is a 2-node
   synthetic; per-question full-CPT request/output sizes and exact
   inference wall/RSS on clinical-sized tables await provider-estimated
   CPTs (S43/S45) and S39 admission. Remediation: re-run
   `capacity.measure` per admitted package once estimated CPTs exist;
   set final admission/resource limits from those numbers.
5. **Single-sample bench + TestClient transport.** Wall/RSS numbers are
   one sample through in-process HTTP, not socket/edge latency;
   p95s above are loopback TestClient figures. Remediation: repeat
   bench N≥30 and load runs through edge HTTP on the deployment host.
6. **`saves.failures` is a hardwired honest zero** (no ledger until S47
   counters). Remediation: S47 adds real save/inference failure
   counters; update `metrics.save_failures` and this report.
7. **Load-run rows remain in the dev DB** (50 + 1000 synthetic patients
   created by §2a–§2b). They are clearly labeled synthetic and never
   migrate to test/owner data, but a cleanup pass on the dev DB is due.
8. **No live-provider smoke, no HA claim.** Absence of credentials is an
   explicit unrun check; single-host failure modes stand as documented
   in plan.md §11.
