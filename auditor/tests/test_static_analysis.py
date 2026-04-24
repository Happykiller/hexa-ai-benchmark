import sys
from pathlib import Path

AUDITOR_DIR = Path(__file__).resolve().parents[1]
if str(AUDITOR_DIR) not in sys.path:
    sys.path.insert(0, str(AUDITOR_DIR))

from modules.static_analysis import CodeQualityChecker, HexagonalComplianceChecker


def test_hexagonal_checker_detects_forbidden_imports_in_string_literals(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    core_dir = project / "src" / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "usecase.ts").write_text(
        'import thing from "../adapters/repository";\nexport const value = thing;\n',
        encoding="utf-8",
    )

    result = HexagonalComplianceChecker(str(project)).check()

    assert result["status"] == "FAILED"
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
