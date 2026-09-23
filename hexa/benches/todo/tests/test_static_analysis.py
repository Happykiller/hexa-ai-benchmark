from pathlib import Path

from hexa.benches.todo.auditor.main import TraceabilityValidator
from hexa.benches.todo.auditor.modules.static_analysis import (
    AuthImplementationChecker,
    CodeQualityChecker,
    CodeSmellAnalyzer,
    HexagonalComplianceChecker,
    ProjectStatsAnalyzer,
    ReadmeChecker,
)


def test_hexagonal_checker_detects_forbidden_imports_in_string_literals(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    core_dir = project / "src" / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "usecase.ts").write_text(
        'import thing from "../adapters/repository";\nexport const value = thing;\n',
        encoding="utf-8",
    )

    result = HexagonalComplianceChecker(str(project)).check()

    assert result["status"] == "KO"
    assert result["violations"]
    assert result["violations"][0]["file"] == "src/core/usecase.ts"


def test_hexagonal_core_purity_ratio(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    core_dir = project / "src" / "core"
    core_dir.mkdir(parents=True)
    # Pure: only relative imports.
    (core_dir / "task.ts").write_text(
        'import { Task } from "./entities/task";\nexport const x = Task;\n', encoding="utf-8"
    )
    # Pure despite a bare specifier: InversifyJS / reflect-metadata are allowed in core.
    (core_dir / "usecase.ts").write_text(
        'import "reflect-metadata";\nimport { injectable } from "inversify";\nexport class UC {}\n',
        encoding="utf-8",
    )
    # Impure: pulls an infrastructure library into the domain.
    (core_dir / "leaky.ts").write_text(
        'import mongoose from "mongoose";\nexport const m = mongoose;\n', encoding="utf-8"
    )
    # Test files are excluded from the purity ratio.
    (core_dir / "task.test.ts").write_text(
        'import axios from "axios";\nit("x", () => {});\n', encoding="utf-8"
    )

    result = HexagonalComplianceChecker(str(project)).check()

    assert result["core_files"] == 3
    assert result["pure_core_files"] == 2
    assert result["core_purity_ratio"] == round(2 / 3, 4)
    assert any("leaky.ts" in f["file"] for f in result["impure_core_files"])


def test_quality_checker_counts_any_in_tsx_files(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    src_dir = project / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "resolver.tsx").write_text(
        "export const Resolver = (props: any) => <div>{props.value}</div>;\n",
        encoding="utf-8",
    )

    result = CodeQualityChecker(str(project)).check_any_usage()

    assert result["ts_files"] == 1
    assert result["any_count"] == 1


def test_traceability_validator_reports_wall_time_consistency_separately(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "audit_trace.json").write_text(
        (
            "{"
            '"meta":{"prompt_version":"2605291055","model":"gpt-test"},'
            '"summary":{"total_turns":2,"total_tool_calls":4,"total_wall_time_seconds":1200},'
            '"phases":[{"start_time":"2026-05-11T10:00:00Z","end_time":"2026-05-11T10:05:00Z","turns_in_phase":2,"tool_calls_in_phase":4}]'
            "}"
        ),
        encoding="utf-8",
    )

    result = TraceabilityValidator(str(project)).validate()

    assert result["status"] == "OK"
    assert result["wall_time_consistency"]["status"] == "KO"
    assert (
        "differs from summed phases by more than 10%" in result["wall_time_consistency"]["remarks"]
    )


def test_traceability_validator_rejects_inconsistent_turn_summary(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "audit_trace.json").write_text(
        (
            "{"
            '"meta":{"prompt_version":"2605291055","model":"gpt-test"},'
            '"summary":{"total_turns":20,"total_tool_calls":4,"total_wall_time_seconds":300},'
            '"phases":[{"start_time":"2026-05-11T10:00:00Z","end_time":"2026-05-11T10:05:00Z","turns_in_phase":2,"tool_calls_in_phase":4}]'
            "}"
        ),
        encoding="utf-8",
    )

    result = TraceabilityValidator(str(project)).validate()

    assert result["status"] == "KO"
    assert "summary.total_turns differs from summed phases by more than 10%" in result["error"]


def test_traceability_validator_requires_prompt_version(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "audit_trace.json").write_text(
        (
            "{"
            '"meta":{"model":"gpt-test"},'
            '"summary":{"total_turns":1,"total_tool_calls":1,"total_wall_time_seconds":60},'
            '"phases":[{"start_time":"2026-05-11T10:00:00Z","end_time":"2026-05-11T10:01:00Z","turns_in_phase":1,"tool_calls_in_phase":1}]'
            "}"
        ),
        encoding="utf-8",
    )

    result = TraceabilityValidator(str(project)).validate()

    assert result["status"] == "KO"
    assert "meta.prompt_version is required" in result["error"]


def test_hexagonal_checker_ignores_forbidden_imports_inside_comments(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    core_dir = project / "src" / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "usecase.ts").write_text(
        '// import repo from "../adapters/repository";\nexport const value = "ok";\n',
        encoding="utf-8",
    )

    result = HexagonalComplianceChecker(str(project)).check()

    assert result["status"] == "OK"
    assert result["violations"] == []


def test_readme_checker_requires_real_markdown_headings(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "README.md").write_text(
        "This project mentions docker and graphql and architecture in prose only.\n",
        encoding="utf-8",
    )

    result = ReadmeChecker(str(project)).check()

    assert result["status"] == "PARTIEL"
    assert result["indicators"]["has_docker_info"] is False
    assert result["indicators"]["has_architecture_section"] is False


def test_auth_checker_ignores_auth_keywords_in_comments(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    src_dir = project / "src" / "entrypoints"
    src_dir.mkdir(parents=True)
    (project / "package.json").write_text('{"dependencies": {}}', encoding="utf-8")
    (src_dir / "resolver.ts").write_text(
        '// login(email: "x")\n// verifyToken(token)\nexport const noop = true;\n',
        encoding="utf-8",
    )

    result = AuthImplementationChecker(str(project)).check()

    assert result["indicators"]["auth_mutations_present"] is False
    assert result["indicators"]["auth_guard_present"] is False


def test_readme_rejects_empty_headings(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "README.md").write_text(
        "# Title\n## Architecture\n## Installation\n## API GraphQL\n## Docker\n",
        encoding="utf-8",
    )

    result = ReadmeChecker(str(project)).check()

    # Headings exist but carry no content → must not score.
    assert result["indicators"]["has_architecture_section"] is False
    assert result["indicators"]["has_docker_info"] is False


def test_readme_accepts_real_content_with_subsections_and_code(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "README.md").write_text(
        "# Title\n## Installation\n"
        "### Prerequisites\n"
        "Node.js and Docker are required to build and run the full stack locally end to end.\n"
        "```bash\n# install host tooling\nmake setup\n```\n"
        "## Docker\nThe compose file orchestrates api, mongodb and mysql services together for you.\n",
        encoding="utf-8",
    )

    result = ReadmeChecker(str(project)).check()

    # Code-fence "# install" comment must NOT be treated as a heading, and the
    # Installation body (incl. its subsection) must count.
    assert result["indicators"]["has_installation_section"] is True
    assert result["indicators"]["has_docker_info"] is True


def test_project_stats_measures_assertion_ratio(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    tests_dir = project / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "real.test.ts").write_text(
        "it('x', () => { expect(1).toBe(1); });", encoding="utf-8"
    )
    (tests_dir / "fake.test.ts").write_text(
        "it('y', () => { /* no real assertion here */ });", encoding="utf-8"
    )

    stats = ProjectStatsAnalyzer(str(project)).analyze()

    assert stats["total_tests"] == 2
    assert stats["test_files_with_assertions"] == 1
    assert stats["assertion_ratio"] == 0.5


def test_codesmell_flags_empty_placeholder_files(tmp_path: Path) -> None:
    src = tmp_path / "deliverable" / "src"
    src.mkdir(parents=True)
    (src / "comment_only.ts").write_text("// placeholder, nothing here\n", encoding="utf-8")
    (src / "blank.ts").write_text("\n\n", encoding="utf-8")
    (src / "real.ts").write_text("export const value = 42;\n", encoding="utf-8")

    result = CodeSmellAnalyzer(str(tmp_path / "deliverable")).analyze()

    empty = next(m for m in result["all_maluses"] if m["id"] == "empty_source_files")
    assert empty["status"] == "DETECTE"
    assert empty["count"] >= 2


def test_code_smell_one_liner_is_not_empty_and_sdl_health_detected(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    src = project / "src"
    src.mkdir(parents=True)
    # Dense one-liner starting with an import: real code, not a placeholder.
    (src / "dense.ts").write_text(
        "import bcrypt from 'bcryptjs'; export class H { hash(v: string) { return bcrypt.hash(v, 12); } }\n",
        encoding="utf-8",
    )
    (src / "empty1.ts").write_text("import 'reflect-metadata';\n// nothing\n", encoding="utf-8")
    (src / "empty2.ts").write_text("import {\n  a,\n  b,\n} from './x';\n\n", encoding="utf-8")
    (src / "schema.ts").write_text(
        "export const typeDefs = `\n  type Query {\n    health: String!\n    tasks: [Task!]!\n  }\n`;\n",
        encoding="utf-8",
    )

    result = CodeSmellAnalyzer(str(project)).analyze()
    empty = next(m for m in result["all_maluses"] if m["id"] == "empty_source_files")
    assert empty["count"] == 2
    health = next(b for b in result["all_bonuses"] if "Healthcheck" in b["reason"])
    assert health["status"] == "OK"


def test_auth_guard_detects_resolver_helpers_and_thrown_auth_errors(tmp_path: Path) -> None:
    for body in (
        "export function requireUser(ctx: Ctx) { return ctx.user; }",
        "if (!ctx.user) { throw new UnauthenticatedError('missing token'); }",
    ):
        project = tmp_path / body[:12].replace(" ", "_")
        (project / "src").mkdir(parents=True)
        (project / "src" / "guard.ts").write_text(body + "\n", encoding="utf-8")
        result = AuthImplementationChecker(str(project)).check()
        assert result["indicators"]["auth_guard_present"] is True, body

    bare = tmp_path / "bare"
    (bare / "src").mkdir(parents=True)
    (bare / "src" / "codes.ts").write_text(
        "export const CODE = 'UNAUTHENTICATED';\n", encoding="utf-8"
    )
    assert AuthImplementationChecker(str(bare)).check()["indicators"]["auth_guard_present"] is False
