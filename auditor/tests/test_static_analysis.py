import sys
from pathlib import Path

AUDITOR_DIR = Path(__file__).resolve().parents[1]
if str(AUDITOR_DIR) not in sys.path:
    sys.path.insert(0, str(AUDITOR_DIR))

from main import TraceabilityValidator
from modules.static_analysis import AuthImplementationChecker, CodeQualityChecker, HexagonalComplianceChecker, ReadmeChecker


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


def test_traceability_validator_rejects_inconsistent_summary(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    (project / "audit_trace.json").write_text(
        (
            "{"
            '"meta":{"model":"gpt-test"},'
            '"summary":{"total_turns":20,"total_tool_calls":40,"total_wall_time_seconds":1200},'
            '"phases":[{"start_time":"2026-05-11T10:00:00Z","end_time":"2026-05-11T10:05:00Z","turns_in_phase":2,"tool_calls_in_phase":4}]'
            "}"
        ),
        encoding="utf-8",
    )

    result = TraceabilityValidator(str(project)).validate()

    assert result["status"] == "KO"
    assert "differs from summed phases by more than 10%" in result["error"]


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
