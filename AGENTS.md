# Repository Instructions for AI Agents

This file provides guidance to AI agents (Claude, Gemini, Codex, etc.) when working with code in this repository.

## Project Overview

**Hexa-AI Benchmark** is an industrial-grade framework that evaluates AI agents' ability to deliver a complete, production-ready **Todo List Multi-Database Hexagonal Architecture** application. The benchmark scores agents across four pillars: Operationality (50%), Architectural Rigor (25%), Software Quality (15%), and Discipline & Traceability (10%).

The Python **auditor** runs a full validation cycle against a deliverable folder submitted by an agent. It produces a scored markdown report.

## Running the Auditor

```bash
# Install auditor dependencies (once)
pip install -r auditor/requirements.txt

# Full audit (static + dynamic)
python auditor/main.py analyze livrables/<DELIVERABLE_FOLDER>

# Static-only audit (skip Docker/E2E)
python auditor/main.py analyze livrables/<DELIVERABLE_FOLDER> --skip-dynamic
```

## Running Auditor Tests

```bash
# All tests
pytest auditor/tests/

# Single test file
pytest auditor/tests/test_static_analysis.py

# Single test by name
pytest auditor/tests/test_static_analysis.py -k "test_hexagonal_compliance"
```

## Deliverable Makefile Targets (called by the auditor on the evaluated project)

The auditor invokes these targets sequentially inside the deliverable directory:

| Target | Purpose |
|---|---|
| `make setup` | Install dependencies (run once before `make start`) |
| `make lint` | ESLint + Prettier via Docker |
| `make build` | TypeScript compilation via Docker |
| `make test` | Jest unit/integration tests via Docker |
| `make start` | Spin up Docker Compose (API + MongoDB + MySQL) |

**Eliminatory threshold**: if `make build` fails, the total score is capped at 40/100.

## Architecture

### Audit Pipeline (`auditor/main.py`)

`main.py` is the orchestrator. It initializes an `audit_db` (a nested JSON structure accumulating phases → steps → indicators) and drives the pipeline:

1. **Phase 1 — Static Analysis**: Runs all static checkers in sequence against source files.
2. **Phase 2 — Dynamic Analysis**: Executes make targets, spins up Docker, runs E2E and performance tests.
3. **Phase 3 — Traceability**: Parses `audit_trace.json` from the deliverable for agent timing/context metrics.
4. **Finalization**: Calls `_finalize_audit_db()` to compute Fibonacci-weighted scores per indicator.
5. **Report**: Renders `auditor/templates/report.md` via Jinja2.

### Static Analysis (`auditor/modules/static_analysis.py`)

Five checkers, each returning structured indicator lists:

- **`HexagonalComplianceChecker`** — enforces layer isolation (Core must not import from adapters/infrastructure/entrypoints); uses regex to strip comments before scanning imports.
- **`CodeQualityChecker`** — counts TypeScript `any` usages; scores inversely (100 − count×2).
- **`ProjectStatsAnalyzer`** — counts files, TS/TSX files, LOC, test files, project size in KB.
- **`CodeSmellAnalyzer`** — detects bonuses (custom errors, env validation, healthcheck, Relay pagination, structured logging) and maluses (AbstractFactory over-abstraction, extreme file fragmentation >30% files <10 lines).
- **`ReadmeChecker`** — validates README presence and required sections (Architecture, Installation, API, Docker), each of which must carry real content, not just an empty heading.

**Challenge profile & registry (`auditor/challenges.py`)** — `ChallengeProfile` holds everything Todo-specific (GraphQL endpoint, expected E2E/auth step names + weights, layer names) so the orchestrator is challenge-agnostic. `TODO_STATIC_CHECKERS` is a declarative registry: each static checker carries an `emit` mapper that reuses `_append_indicator`, so adding a static control = one registry entry, no `main.py` edit.

**Supply-chain & DevEx (`auditor/modules/supply_chain.py`)** — `DevExChecker` (tsconfig `strict` actually enabled, ESLint config, CI workflows, sane `.gitignore`; scored in phase 2 / step 7, quality bucket), plus `SecretsScanner` and `NpmAuditChecker` (maluses).

### Dynamic Analysis (`auditor/modules/dynamic_analysis.py`)

- **`MakefileRunner`** — runs a make target (5-min timeout), captures stdout/stderr and exit code.
- **`DockerOrchestrator`** — starts the stack, polls `http://localhost:4000/graphql` health (max 30 retries × 2s), extracts container states via `docker compose ps --format json`.
- **`E2EFunctionalTester`** — GraphQL scenario validating task-dependency blocking logic. Critical: the "Close B while A is open" step must fail with an error containing `depend|blocked|prerequisite|precondition`; an independent (no-dependency) task must still close successfully (anti "always-block" gaming).
- **`AuthTester`** — auth + security E2E: unauth blocked, register/login, tampered token, plus real depth — `alg:none` rejected, foreign-signature rejected, per-user task isolation, exact `UNAUTHENTICATED` code, weak-password rejection (JWTs forged with the stdlib, no extra dependency).
- **`PerformanceBenchmarker`** — 50 iterations of a GraphQL query; reports avg latency, P95, and error rate.

### Scoring System (`auditor/scoring_config.py`)

Two scoring configs:

- **`TRACE_SCORING_CONFIG`** — evaluates agent trace metrics: total duration, avg duration, max/avg context usage.
- **`TECHNICAL_STATS_SCORING_CONFIG`** — evaluates deliverable codebase metrics: total files, TS/TSX files, LOC, test files, project size.

Scoring algorithm:
- Indicators have a **rank** (used for Fibonacci weighting: rank 2 = 1 pt, rank 3 = 2 pts, …) or an explicit `weight`.
- Each indicator's value is matched to a **band** (list of `{min, max, score_ratio}`) → `final_score = weight × ratio`.
- Maluses use negative polarity; bonuses use positive polarity.
- Phase score = sum of step scores; total = sum of phase scores.

### Deliverable Layout (expected structure)

```
livrables/<TIMESTAMP_MODEL_TEMP>/
├── audit_trace.json          # Agent run trace (phases, ISO datetimes, context %)
├── Makefile                  # setup / lint / build / test / start targets
├── docker-compose.yml        # services: api, mongo, mysql
├── package.json
├── tsconfig.json             # strict mode required
├── src/
│   ├── core/                 # Domain — must NOT import from other layers
│   ├── adapters/
│   ├── infrastructure/
│   └── entrypoints/
└── README.md                 # Must contain: Architecture, Installation, API, Docker sections
```

## Key Constraints & Gotchas

- **Layer isolation**: `src/core/` must not contain imports from `adapters/`, `infrastructure/`, or `entrypoints/`. Violations are scored as architectural failures.
- **GraphQL endpoint**: the auditor assumes `http://localhost:4000/graphql` for all dynamic tests.
- **`audit_trace.json`**: phases must include ISO-8601 datetimes and context usage percentages; missing or malformed traces score 0 on Phase 3.
- **Docker Compose version field**: presence of `attribute version is obsolete` in compose output is detected and penalized.
- **TypeScript `any`**: the regex also matches `as any`, `<any>`, etc., excluding comments.
