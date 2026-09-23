from pathlib import Path

from hexa.benches.todo.auditor.main import TraceabilityValidator
from hexa.benches.todo.auditor.modules.static_analysis import (
    HexagonalComplianceChecker,
    ReadmeChecker,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_minimal_valid_fixture_passes_readme_and_trace_checks() -> None:
    project = FIXTURES_DIR / "minimal_valid"

    readme = ReadmeChecker(str(project)).check()
    trace = TraceabilityValidator(str(project)).validate()

    assert readme["found"] is True
    assert readme["status"] in ("OK", "PARTIEL")
    assert trace["status"] == "OK"


def test_hexagonal_violation_fixture_is_detected() -> None:
    project = FIXTURES_DIR / "hexagonal_violation"

    result = HexagonalComplianceChecker(str(project)).check()

    assert result["status"] == "KO"
    assert result["violations"]


def test_bad_trace_fixture_is_rejected() -> None:
    project = FIXTURES_DIR / "bad_trace"

    result = TraceabilityValidator(str(project)).validate()

    assert result["status"] == "KO"
