import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

AUDITOR_DIR = Path(__file__).resolve().parents[1]
if str(AUDITOR_DIR) not in sys.path:
    sys.path.insert(0, str(AUDITOR_DIR))

from main import _compute_final_score_summary, _compute_score_caps, analyze
from modules.dynamic_analysis import AuthTester, DockerOrchestrator, E2EFunctionalTester, _mint_jwt


def test_docker_orchestrator_times_out_make_start(tmp_path: Path) -> None:
    orchestrator = DockerOrchestrator(str(tmp_path))

    with patch(
        "modules.dynamic_analysis.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["make", "start"], timeout=120),
    ):
        result = orchestrator.start()

    assert result["status"] == "KO"
    assert "timed out" in result["error"]


def test_docker_orchestrator_exposes_stderr_on_nonzero_exit(tmp_path: Path) -> None:
    orchestrator = DockerOrchestrator(str(tmp_path))
    fake_result = subprocess.CompletedProcess(
        args=["make", "start"], returncode=1, stdout="", stderr="Error: port already in use"
    )

    with patch("modules.dynamic_analysis.subprocess.run", return_value=fake_result):
        result = orchestrator.start()

    assert result["status"] == "KO"
    assert result["exit_code"] == 1
    assert "port already in use" in result["stderr"]


def test_e2e_rejects_unrelated_graphql_errors() -> None:
    tester = E2EFunctionalTester("http://example.test/graphql")
    responses = iter(
        [
            {"data": {"tasks": []}},
            {"data": {"createTask": {"id": "A", "status": "OPEN"}}},
            {"data": {"tasks": [{"id": "A", "title": "Task A", "status": "OPEN"}]}},
            {"data": {"createTask": {"id": "B", "status": "OPEN"}}},
            {"errors": [{"message": "Authentication required"}]},
            {"data": {"updateTaskStatus": {"status": "COMPLETED"}}},
            {"data": {"updateTaskStatus": {"status": "COMPLETED"}}},
            {"data": {"createTask": {"id": "IND", "status": "OPEN"}}},
            {"data": {"updateTaskStatus": {"status": "COMPLETED"}}},
        ]
    )

    with patch.object(tester, "_post", side_effect=lambda _: next(responses)):
        results = tester.run_scenario()

    blocked_step = next(step for step in results if step["step"] == "Close B (Should Fail)")
    assert blocked_step["success"] is False


def test_main_marks_e2e_as_skipped_when_dynamic_phase_is_disabled(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()

    def fake_run_target(target: str):
        return {"status": "OK", "output": "", "error": "", "exit_code": 0}

    with patch("main.MakefileRunner.run_target", side_effect=fake_run_target), \
        patch("main.HexagonalComplianceChecker.check", return_value={"status": "OK", "score": 100, "rules": []}), \
        patch("main.CodeQualityChecker.check_any_usage", return_value={"status": "OK", "score": 100, "any_count": 0, "ts_files": 0}), \
        patch("main.ProjectStatsAnalyzer.analyze", return_value={"total_files": 0, "total_ts_files": 0, "total_lines": 0, "total_size_kb": 0, "total_tests": 0}), \
        patch("main.CodeSmellAnalyzer.analyze", return_value={"total_bonus": 0, "total_malus": 0, "bonuses": [], "maluses": [], "all_bonuses": [], "all_maluses": []}), \
        patch("main.Environment.get_template") as get_template:
        get_template.return_value.render.return_value = "report"
        analyze.callback(str(project), True, False, False)

    report_files = list(project.glob("audit_report_*.md"))
    assert report_files, "no audit_report_<timestamp>.md found in project"


def test_main_force_dynamic_runs_docker_even_when_build_fails(tmp_path: Path) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()

    def fake_run_target(target: str):
        status = "KO" if target == "build" else "OK"
        return {"status": status, "output": "", "error": "", "exit_code": 1 if status == "KO" else 0}

    with patch("main.MakefileRunner.run_target", side_effect=fake_run_target), \
        patch("main.DockerOrchestrator.start", return_value={"status": "KO", "error": "runtime failed"}) as start, \
        patch("main.HexagonalComplianceChecker.check", return_value={"status": "OK", "score": 100, "rules": []}), \
        patch("main.CodeQualityChecker.check_any_usage", return_value={"status": "OK", "score": 100, "any_count": 0, "ts_files": 0}), \
        patch("main.ProjectStatsAnalyzer.analyze", return_value={"total_files": 0, "total_ts_files": 0, "total_lines": 0, "total_size_kb": 0, "total_tests": 0}), \
        patch("main.CodeSmellAnalyzer.analyze", return_value={"total_bonus": 0, "total_malus": 0, "bonuses": [], "maluses": [], "all_bonuses": [], "all_maluses": []}), \
        patch("main.Environment.get_template") as get_template:
        get_template.return_value.render.return_value = "report"
        analyze.callback(str(project), False, True, True)

    start.assert_called_once_with(fresh=True)


def test_compute_score_caps_limits_score_to_40_when_cap_is_lower() -> None:
    result = _compute_score_caps(
        75.0,
        [{"id": "build_failed", "max_percentage": 40, "reason": "make build failed"}],
    )

    assert result["raw_percentage"] == 75.0
    assert result["final_percentage"] == 40
    assert result["capped"] is True


def test_compute_final_score_summary_normalizes_buckets_and_caps_bonus_malus() -> None:
    audit_db = {
        "meta": {"score_cap_reasons": []},
        "phases": [
            {"number": 4, "raw_total": 12},
        ],
        "indicators": [
            {
                "kind": "scored",
                "phase_number": 1,
                "step_number": 1,
                "polarity": "positive",
                "score": 20,
                "max_score": 40,
            },
            {
                "kind": "scored",
                "phase_number": 2,
                "step_number": 1,
                "polarity": "positive",
                "score": 10,
                "max_score": 20,
            },
            {
                "kind": "scored",
                "phase_number": 2,
                "step_number": 2,
                "polarity": "positive",
                "score": 5,
                "max_score": 10,
            },
            {
                "kind": "scored",
                "phase_number": 3,
                "step_number": 1,
                "polarity": "positive",
                "score": 4,
                "max_score": 8,
            },
        ],
    }

    summary = _compute_final_score_summary(audit_db)

    assert summary["bucket_scores"]["operationality"]["normalized_score"] == 25
    assert summary["bucket_scores"]["architecture"]["normalized_score"] == 12.5
    assert summary["bucket_scores"]["quality"]["normalized_score"] == 7.5
    assert summary["bucket_scores"]["traceability"]["normalized_score"] == 5
    assert summary["bonus_malus"]["capped_adjustment"] == 5
    assert summary["final_percentage"] == 55


def _make_fake_graphql_server(secure: bool):
    """Stateful in-memory GraphQL server for AuthTester. ``secure`` toggles JWT
    verification and per-user isolation so tests can assert discrimination."""
    state = {"users": {}, "tasks": [], "n": 0}

    def post(query, token=None):
        if "register(" in query and 'password: "123"' in query:
            if secure:
                return {"errors": [{"message": "weak password", "extensions": {"code": "BAD_USER_INPUT"}}]}
            state["n"] += 1
            tok = f"t{state['n']}"
            state["users"][tok] = "weak"
            return {"data": {"register": {"token": tok}}}
        if "register(" in query or "login(" in query:
            match = re.search(r'email:\s*"([^"]+)"', query)
            email = match.group(1) if match else "x"
            state["n"] += 1
            tok = f"t{state['n']}-{email}"
            state["users"][tok] = email
            key = "register" if "register(" in query else "login"
            return {"data": {key: {"token": tok, "user": {"id": email, "email": email}}}}
        authed = (token in state["users"]) if secure else (token is not None)
        if not authed:
            return {"errors": [{"message": "unauthenticated", "extensions": {"code": "UNAUTHENTICATED"}}]}
        if "createTask" in query:
            state["n"] += 1
            tid = f"task{state['n']}"
            state["tasks"].append({"id": tid, "owner": token})
            return {"data": {"createTask": {"id": tid, "status": "OPEN"}}}
        if "tasks" in query:
            rows = [{"id": t["id"]} for t in state["tasks"] if (not secure or t["owner"] == token)]
            return {"data": {"tasks": rows}}
        return {"data": {}}

    return post


_SECURITY_STEPS = [
    "Auth: Token alg=none rejeté",
    "Auth: Signature étrangère rejetée",
    "Auth: Isolation inter-utilisateurs",
    "Auth: Mot de passe faible refusé",
]


def test_mint_jwt_alg_none_is_unsigned() -> None:
    token = _mint_jwt({"sub": "x"}, alg="none")
    assert token.count(".") == 2 and token.endswith(".")


def test_mint_jwt_hs256_is_signed() -> None:
    token = _mint_jwt({"sub": "x"}, alg="HS256", secret="k")
    assert token.count(".") == 2 and token.split(".")[2] != ""


def test_auth_tester_security_steps_pass_on_secure_server() -> None:
    tester = AuthTester("http://example.test/graphql")
    with patch.object(tester, "_post", side_effect=_make_fake_graphql_server(secure=True)):
        results = {r["step"]: r["success"] for r in tester.run_scenario()}

    assert len(results) == 10
    for step in _SECURITY_STEPS + ["Auth: Code UNAUTHENTICATED exact"]:
        assert results[step] is True, f"secure server should pass {step}"


def test_auth_tester_security_steps_fail_on_insecure_server() -> None:
    tester = AuthTester("http://example.test/graphql")
    with patch.object(tester, "_post", side_effect=_make_fake_graphql_server(secure=False)):
        results = {r["step"]: r["success"] for r in tester.run_scenario()}

    for step in _SECURITY_STEPS:
        assert results[step] is False, f"insecure server should fail {step}"
