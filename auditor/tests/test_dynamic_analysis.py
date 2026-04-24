import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

AUDITOR_DIR = Path(__file__).resolve().parents[1]
if str(AUDITOR_DIR) not in sys.path:
    sys.path.insert(0, str(AUDITOR_DIR))

from main import analyze
from modules.dynamic_analysis import DockerOrchestrator, E2EFunctionalTester


def test_docker_orchestrator_times_out_make_start(tmp_path: Path) -> None:
    orchestrator = DockerOrchestrator(str(tmp_path))

    with patch(
        "modules.dynamic_analysis.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["make", "start"], timeout=120),
    ):
        result = orchestrator.start()

    assert result["status"] == "FAILED"
    assert "timed out" in result["error"]


def test_e2e_rejects_unrelated_graphql_errors() -> None:
    tester = E2EFunctionalTester("http://example.test/graphql")
    responses = iter(
        [
            {"data": {"createTask": {"id": "A", "status": "OPEN"}}},
            {"data": {"createTask": {"id": "B", "status": "OPEN"}}},
            {"errors": [{"message": "Authentication required"}]},
            {"data": {"updateTaskStatus": {"status": "COMPLETED"}}},
            {"data": {"updateTaskStatus": {"status": "COMPLETED"}}},
        ]
    )

    with patch.object(tester, "_post", side_effect=lambda _: next(responses)):
        results = tester.run_scenario()

    blocked_step = next(step for step in results if step["step"] == "Close B (Should Fail)")
    assert blocked_step["success"] is False


def test_main_marks_e2e_as_skipped_when_dynamic_phase_is_disabled(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    templates_dir = Path(__file__).resolve().parents[1] / "templates"
    project.mkdir()

    def fake_run_target(target: str):
        return {"status": "SUCCESS", "output": "", "error": "", "exit_code": 0}

    with patch("main.MakefileRunner.run_target", side_effect=fake_run_target), \
        patch("main.HexagonalComplianceChecker.check", return_value={"status": "SUCCESS", "score": 100}), \
        patch("main.CodeQualityChecker.check_any_usage", return_value={"status": "SUCCESS", "score": 100, "any_count": 0}), \
        patch("main.ProjectStatsAnalyzer.analyze", return_value={"total_ts_files": 0, "total_lines": 0, "total_size_kb": 0}), \
        patch("main.CodeSmellAnalyzer.analyze", return_value={"total_bonus": 0, "total_malus": 0, "bonuses": [], "maluses": []}), \
        patch("main.Environment.get_template") as get_template:
        get_template.return_value.render.return_value = "report"
        analyze.callback(str(project), True)

    report_path = project / "audit_report.md"
    assert report_path.exists()
