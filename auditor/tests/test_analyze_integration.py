"""End-to-end smoke test for the `analyze` orchestrator.

Runs the real static-analysis + scoring + Jinja report pipeline against a realistic
fixture deliverable in `--skip-dynamic` mode. Only the external `make` subprocess is
stubbed; everything else executes for real. Purpose: catch any crash / regression in the
pipeline *before* launching a real model benchmark.

Output is redirected into a tmp dir via HEXA_AUDIT_OUTPUT_DIR so the repo's cr_audits/
is never touched.
"""

import json

from click.testing import CliRunner
from main import cli

_PACKAGE_JSON = {
    "name": "todo-hexa",
    "version": "1.0.0",
    "scripts": {"build": "tsc", "test": "jest", "lint": "eslint ."},
    "dependencies": {
        "mongoose": "^8.0.0",
        "mysql2": "^3.6.0",
        "inversify": "^6.0.0",
        "reflect-metadata": "^0.2.0",
        "jsonwebtoken": "^9.0.0",
        "bcrypt": "^5.1.0",
        "graphql": "^16.8.0",
        "@apollo/server": "^4.9.0",
    },
    "devDependencies": {"typescript": "^5.3.0", "jest": "^29.0.0", "eslint": "^8.0.0"},
}

_README = """# Todo Hexa

## Architecture
Hexagonal architecture with an isolated core domain, adapters for MongoDB and MySQL,
and a GraphQL entrypoint. The core never imports infrastructure.

## Installation
Run `make setup` to install dependencies, then `make start` to boot the stack.

## API
GraphQL API exposed at http://localhost:4000/graphql with task and auth mutations.

## Docker
`docker compose` starts the api, mongo and mysql services. Use `make start`.
"""

_MAKEFILE = """setup:
\tnpm ci
lint:
\tnpm run lint
build:
\tnpm run build
test:
\tnpm test
start:
\tdocker compose up -d
down:
\tdocker compose down -v
"""

_COMPOSE = """services:
  api:
    build: .
    ports:
      - "4000:4000"
  mongo:
    image: mongo:7
  mysql:
    image: mysql:8
"""

_TRACE = {
    "meta": {"prompt_version": "2606082200", "model": "claude-sonnet-4-6"},
    "summary": {
        "total_turns": 10,
        "total_tool_calls": 40,
        "total_wall_time_seconds": 1200,
        # $0.90 at claude-sonnet pricing ($2/$10) → cost band ratio 0.75 (a *partial* band),
        # so the cost pillar must score > 0 (guards the graduated-scoring regression).
        "total_input_tokens": 200000,
        "total_output_tokens": 50000,
        "total_cached_input_tokens": 0,
    },
    "phases": [
        {
            "start_time": "2026-07-01T10:00:00Z",
            "end_time": "2026-07-01T10:20:00Z",
            "turns_in_phase": 10,
            "tool_calls_in_phase": 40,
        }
    ],
}


def _write_fixture(root):
    (root / "src" / "core").mkdir(parents=True)
    (root / "src" / "adapters").mkdir(parents=True)
    (root / "src" / "entrypoints").mkdir(parents=True)

    (root / "src" / "core" / "task.ts").write_text(
        "export class Task {\n  constructor(public readonly id: string, public done = false) {}\n}\n",
        encoding="utf-8",
    )
    (root / "src" / "adapters" / "task.mongo.repository.ts").write_text(
        "import mongoose from 'mongoose';\nexport class TaskMongoRepository {}\n",
        encoding="utf-8",
    )
    (root / "src" / "adapters" / "user.mysql.repository.ts").write_text(
        "import { createPool } from 'mysql2';\nexport class UserMysqlRepository {}\n",
        encoding="utf-8",
    )
    (root / "src" / "entrypoints" / "resolvers.ts").write_text(
        "import jwt from 'jsonwebtoken';\n"
        "export const resolvers = { Mutation: { register() {}, login() {} } };\n",
        encoding="utf-8",
    )
    (root / "package.json").write_text(json.dumps(_PACKAGE_JSON, indent=2), encoding="utf-8")
    (root / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"strict": True}}, indent=2), encoding="utf-8"
    )
    (root / "README.md").write_text(_README, encoding="utf-8")
    (root / "Makefile").write_text(_MAKEFILE, encoding="utf-8")
    (root / "docker-compose.yml").write_text(_COMPOSE, encoding="utf-8")
    (root / "audit_trace.json").write_text(json.dumps(_TRACE, indent=2), encoding="utf-8")


def test_analyze_skip_dynamic_runs_clean(tmp_path, monkeypatch):
    deliverable = tmp_path / "20260701_1200_test-model_0.2"
    deliverable.mkdir()
    _write_fixture(deliverable)

    out_dir = tmp_path / "cr_audits"
    monkeypatch.setenv("HEXA_AUDIT_OUTPUT_DIR", str(out_dir))

    def fake_run_target(target: str):
        return {"status": "OK", "output": "", "error": "", "exit_code": 0}

    runner = CliRunner()
    monkeypatch.setattr(
        "main.MakefileRunner.run_target",
        lambda self, target: fake_run_target(target),
    )
    result = runner.invoke(cli, ["analyze", str(deliverable), "--skip-dynamic"])

    # Surface the real traceback if the pipeline crashed.
    assert result.exit_code == 0, f"analyze crashed: {result.exception!r}\n{result.output}"

    reports = list(out_dir.glob("cr_*.md"))
    data_files = list(out_dir.glob("cr_*.json"))
    assert reports, "no markdown report was written"
    assert data_files, "no JSON audit data was written"

    data = json.loads(data_files[0].read_text(encoding="utf-8"))
    assert "summary" in data
    assert isinstance(data["summary"].get("percentage_net"), (int, float))
    # The deliverable also keeps its own copy of the report.
    assert list(deliverable.glob("audit_report_*.md"))

    # Cost pillar regression guard: a ~$1.35 session sits in a *partial* cost band
    # (ratio 0.75). The scored cost indicator must award graduated points, not 0
    # (the bug: the cost call gated scoring on ratio >= 1.0 instead of ratio > 0).
    cost_inds = [
        i for i in data["indicators"] if i.get("phase_number") == 6 and i.get("kind") == "scored"
    ]
    assert cost_inds, "no scored cost indicator in phase 6"
    assert cost_inds[0]["score"] > 0, (
        f"cost pillar must score a partial band, got {cost_inds[0]['score']}"
    )


def test_analyze_rejects_conflicting_dynamic_flags(tmp_path, monkeypatch):
    deliverable = tmp_path / "deliverable"
    deliverable.mkdir()
    monkeypatch.setenv("HEXA_AUDIT_OUTPUT_DIR", str(tmp_path / "cr_audits"))

    result = CliRunner().invoke(
        cli, ["analyze", str(deliverable), "--skip-dynamic", "--force-dynamic"]
    )
    assert result.exit_code != 0
