import json
import re
import subprocess
from pathlib import Path
from unittest.mock import patch

from main import (
    _compute_final_score_summary,
    _compute_score_caps,
    _compute_session_cost,
    _normalize_model_id,
    _parse_coverage_by_layer,
    analyze,
)
from modules.dynamic_analysis import (
    AuthTester,
    DockerOrchestrator,
    E2EFunctionalTester,
    _mint_jwt,
    precreate_bind_mount_dirs,
)


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
    # Pre-seed a token so the self-authentication step is skipped and the mocked
    # responses below stay aligned with the functional steps.
    tester = E2EFunctionalTester(
        "http://example.test/graphql", token="pre.baked.tokenvalue0123456789"
    )
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


def test_e2e_self_authenticates_when_no_token_injected() -> None:
    # No token injected (the orchestrator's auth probe could not extract one). The
    # scenario must self-register and recover the token even when the server names
    # the field "accessToken" (non-spec shape), so a working Task domain is exercised
    # instead of collapsing the whole functional run — and the score — on auth wiring.
    responses = iter(
        [
            {"data": {"register": {"accessToken": "hdr.pay.selfauthtokenvalue0123456789"}}},
            {"data": {"tasks": []}},
            {"data": {"createTask": {"id": "A", "status": "OPEN"}}},
            {"data": {"tasks": [{"id": "A", "title": "Task A", "status": "OPEN"}]}},
            {"data": {"createTask": {"id": "B", "status": "OPEN"}}},
            {"errors": [{"message": "Task is blocked by an unmet dependency"}]},
            {"data": {"updateTaskStatus": {"status": "COMPLETED"}}},
            {"data": {"updateTaskStatus": {"status": "COMPLETED"}}},
            {"data": {"createTask": {"id": "IND", "status": "OPEN"}}},
            {"data": {"updateTaskStatus": {"status": "COMPLETED"}}},
        ]
    )
    tester = E2EFunctionalTester("http://example.test/graphql")

    with patch.object(tester, "_post", side_effect=lambda _: next(responses)):
        results = tester.run_scenario()

    assert tester.token == "hdr.pay.selfauthtokenvalue0123456789"
    steps = {r["step"]: r["success"] for r in results}
    assert steps["Create Task A"] is True
    assert steps["Close B (Should Fail)"] is True
    assert steps["Close Independent Task (No Deps)"] is True
    assert len(results) == 8


def test_deep_find_token_tolerant_to_response_shapes() -> None:
    tester = E2EFunctionalTester("http://example.test/graphql")

    assert (
        tester._deep_find_token({"data": {"register": {"token": "a.b.cspecpathtokenvalue000000"}}})
        == "a.b.cspecpathtokenvalue000000"
    )
    assert (
        tester._deep_find_token(
            {"data": {"login": {"accessToken": "x.y.zaltkeytokenvalue111111111"}}}
        )
        == "x.y.zaltkeytokenvalue111111111"
    )
    assert (
        tester._deep_find_token({"data": {"signup": {"jwt": "p.q.rjwtkeytokenvalue22222222222"}}})
        == "p.q.rjwtkeytokenvalue22222222222"
    )
    assert tester._deep_find_token({"errors": [{"message": "boom"}]}) is None
    assert tester._deep_find_token({"data": {"register": {"token": ""}}}) is None


def _make_dependency_server(robust: bool):
    """Stateful GraphQL fake supporting task dependencies. ``robust=False`` mimics a
    naive engine: it checks only the first dependency, accepts arbitrary status values,
    and lets a task depend on a non-existent id — exactly what the adversarial scenario
    must catch."""
    state = {"tasks": {}, "n": 0}

    def post(query):
        if "register(" in query or "login(" in query:
            state["n"] += 1
            key = "register" if "register(" in query else "login"
            return {"data": {key: {"token": f"tok.{state['n']}.xxxxxxxxxxxxxxxxxxxx"}}}
        if "createTask" in query:
            block = re.search(r"dependsOn:\s*\[([^\]]*)\]", query)
            dep_ids = re.findall(r'"([^"]+)"', block.group(1)) if block else []
            if robust and any(d not in state["tasks"] for d in dep_ids):
                return {"errors": [{"message": "dependency does not exist"}]}
            state["n"] += 1
            tid = f"task{state['n']}"
            state["tasks"][tid] = {"status": "OPEN", "deps": dep_ids}
            return {"data": {"createTask": {"id": tid, "status": "OPEN"}}}
        if "updateTaskStatus" in query:
            m = re.search(r'updateTaskStatus\(id:\s*"([^"]+)",\s*status:\s*"([^"]+)"', query)
            tid, status = m.group(1), m.group(2)
            if tid not in state["tasks"]:
                return {"errors": [{"message": "not found"}]}
            if status not in ("OPEN", "COMPLETED"):
                if robust:
                    return {"errors": [{"message": "invalid status value"}]}
                state["tasks"][tid]["status"] = status
                return {"data": {"updateTaskStatus": {"id": tid, "status": status}}}
            if status == "COMPLETED":
                deps = state["tasks"][tid]["deps"]
                to_check = deps if robust else deps[:1]  # naive checks only the first
                if any(state["tasks"].get(d, {}).get("status") != "COMPLETED" for d in to_check):
                    return {"errors": [{"message": "blocked: dependency not completed"}]}
            state["tasks"][tid]["status"] = status
            return {"data": {"updateTaskStatus": {"id": tid, "status": status}}}
        if "tasks" in query:
            return {"data": {"tasks": [{"id": t} for t in state["tasks"]]}}
        return {"data": {}}

    return post


_ADVERSARIAL_STEPS = [
    "Adversarial: Dépendances multiples (toutes requises)",
    "Adversarial: Chaîne de dépendances profonde",
    "Adversarial: Dépendance inexistante rejetée",
    "Adversarial: Statut invalide rejeté",
]


def test_adversarial_scenario_passes_on_robust_engine() -> None:
    tester = E2EFunctionalTester(
        "http://example.test/graphql", token="pre.baked.tokenvalue0123456789"
    )
    with patch.object(tester, "_post", side_effect=_make_dependency_server(robust=True)):
        results = {r["step"]: r["success"] for r in tester.run_adversarial_scenario()}

    assert len(results) == 4
    for step in _ADVERSARIAL_STEPS:
        assert results[step] is True, f"robust engine should pass {step}"


def test_adversarial_scenario_fails_on_naive_engine() -> None:
    tester = E2EFunctionalTester(
        "http://example.test/graphql", token="pre.baked.tokenvalue0123456789"
    )
    with patch.object(tester, "_post", side_effect=_make_dependency_server(robust=False)):
        results = {r["step"]: r["success"] for r in tester.run_adversarial_scenario()}

    # The naive engine (first-dependency-only, accepts arbitrary status, accepts ghost
    # deps) fails exactly the probes targeting those weaknesses — that is the discrimination.
    assert results["Adversarial: Dépendances multiples (toutes requises)"] is False
    assert results["Adversarial: Dépendance inexistante rejetée"] is False
    assert results["Adversarial: Statut invalide rejeté"] is False
    # A single-dependency chain is correctly enforced by any direct-dep checker, so it is
    # a correctness probe rather than a discriminator for this particular naivety.
    assert results["Adversarial: Chaîne de dépendances profonde"] is True


def test_main_marks_e2e_as_skipped_when_dynamic_phase_is_disabled(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    monkeypatch.setenv("HEXA_AUDIT_OUTPUT_DIR", str(tmp_path / "cr_audits"))

    def fake_run_target(target: str):
        return {"status": "OK", "output": "", "error": "", "exit_code": 0}

    with (
        patch("main.MakefileRunner.run_target", side_effect=fake_run_target),
        # HexagonalComplianceChecker / CodeQualityChecker are invoked via the challenges
        # registry (not through `main`), so there is no `main.*` attribute to patch.
        patch(
            "main.ProjectStatsAnalyzer.analyze",
            return_value={
                "total_files": 0,
                "total_ts_files": 0,
                "total_lines": 0,
                "total_size_kb": 0,
                "total_tests": 0,
            },
        ),
        patch(
            "main.CodeSmellAnalyzer.analyze",
            return_value={
                "total_bonus": 0,
                "total_malus": 0,
                "bonuses": [],
                "maluses": [],
                "all_bonuses": [],
                "all_maluses": [],
            },
        ),
        patch("main.Environment.get_template") as get_template,
    ):
        get_template.return_value.render.return_value = "report"
        analyze.callback(str(project), True, False, False)

    report_files = list(project.glob("audit_report_*.md"))
    assert report_files, "no audit_report_<timestamp>.md found in project"


def test_main_force_dynamic_runs_docker_even_when_build_fails(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    monkeypatch.setenv("HEXA_AUDIT_OUTPUT_DIR", str(tmp_path / "cr_audits"))

    def fake_run_target(target: str):
        status = "KO" if target == "build" else "OK"
        return {
            "status": status,
            "output": "",
            "error": "",
            "exit_code": 1 if status == "KO" else 0,
        }

    with (
        patch("main.MakefileRunner.run_target", side_effect=fake_run_target),
        patch(
            "main.DockerOrchestrator.start",
            return_value={"status": "KO", "error": "runtime failed"},
        ) as start,
        # HexagonalComplianceChecker / CodeQualityChecker are invoked via the challenges
        # registry (not through `main`), so there is no `main.*` attribute to patch.
        patch(
            "main.ProjectStatsAnalyzer.analyze",
            return_value={
                "total_files": 0,
                "total_ts_files": 0,
                "total_lines": 0,
                "total_size_kb": 0,
                "total_tests": 0,
            },
        ),
        patch(
            "main.CodeSmellAnalyzer.analyze",
            return_value={
                "total_bonus": 0,
                "total_malus": 0,
                "bonuses": [],
                "maluses": [],
                "all_bonuses": [],
                "all_maluses": [],
            },
        ),
        patch("main.Environment.get_template") as get_template,
    ):
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
            {"number": 4, "raw_total": 12, "positive_points_earned": 12, "negative_points": 0},
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

    # Pinned to v1: this guards the legacy 4-bucket normalisation (50/25/15/10) and
    # therefore the reproducibility of the historical runs.
    summary = _compute_final_score_summary(audit_db, "v1")

    assert summary["bucket_scores"]["operationality"]["normalized_score"] == 25
    assert summary["bucket_scores"]["architecture"]["normalized_score"] == 12.5
    assert summary["bucket_scores"]["quality"]["normalized_score"] == 7.5
    assert summary["bucket_scores"]["traceability"]["normalized_score"] == 5
    assert summary["bonus_malus"]["capped_adjustment"] == 5
    assert summary["final_percentage"] == 55


def _audit_db_base_99(bonus: int = 5, malus: int = 0):
    """Audit DB whose base sums to 99/100 under BOTH scoring versions: the non-cost
    buckets are maxed (ratio 1.0) and traceability sits at 9/10, plus a maxed cost
    bucket (phase 6) that v1 ignores and v2 counts — both totals land on 99."""
    return {
        "meta": {"score_cap_reasons": []},
        "phases": [
            {
                "number": 4,
                "raw_total": bonus + malus,
                "positive_points_earned": bonus,
                "negative_points": malus,
            }
        ],
        "indicators": [
            {
                "kind": "scored",
                "phase_number": 1,
                "step_number": 1,
                "polarity": "positive",
                "score": 50,
                "max_score": 50,
            },
            {
                "kind": "scored",
                "phase_number": 2,
                "step_number": 1,
                "polarity": "positive",
                "score": 25,
                "max_score": 25,
            },
            {
                "kind": "scored",
                "phase_number": 2,
                "step_number": 2,
                "polarity": "positive",
                "score": 15,
                "max_score": 15,
            },
            {
                "kind": "scored",
                "phase_number": 3,
                "step_number": 1,
                "polarity": "positive",
                "score": 9,
                "max_score": 10,
            },
            {
                "kind": "scored",
                "phase_number": 6,
                "step_number": 1,
                "polarity": "positive",
                "score": 12,
                "max_score": 12,
            },
        ],
    }


def test_scoring_v2_bonus_cannot_complete_imperfect_base_to_100() -> None:
    summary = _compute_final_score_summary(_audit_db_base_99(bonus=5), "v2")

    assert summary["base_score"] == 99.0
    # Bonus may only fill half of the remaining 1-pt gap → 99.5, never 100.
    assert summary["bonus_malus"]["effective_bonus"] == 0.5
    assert summary["final_percentage"] == 99.5


def test_scoring_v2_applies_malus_fully_then_partial_bonus() -> None:
    # Realistic case: base 99, a -5 malus, +5 bonus. Malus subtracts fully (→94),
    # bonus fills half the remaining 6-pt gap (→+3) → 97, not 100.
    summary = _compute_final_score_summary(_audit_db_base_99(bonus=5, malus=-5), "v2")

    assert summary["bonus_malus"]["capped_malus"] == -5
    assert summary["bonus_malus"]["effective_bonus"] == 3.0
    assert summary["final_percentage"] == 97.0


def test_parse_coverage_by_layer_aggregates_per_layer(tmp_path: Path) -> None:
    cov_dir = tmp_path / "coverage"
    cov_dir.mkdir()
    summary = {
        "total": {"lines": {"total": 100, "covered": 80, "pct": 80.0}},
        "/app/src/core/createTask.ts": {"lines": {"total": 10, "covered": 9, "pct": 90.0}},
        "/app/src/core/updateTask.ts": {"lines": {"total": 10, "covered": 9, "pct": 90.0}},
        "/app/src/adapters/mongoRepo.ts": {"lines": {"total": 20, "covered": 10, "pct": 50.0}},
        "/app/src/entrypoints/server.ts": {"lines": {"total": 10, "covered": 2, "pct": 20.0}},
    }
    (cov_dir / "coverage-summary.json").write_text(json.dumps(summary), encoding="utf-8")

    result = _parse_coverage_by_layer(str(tmp_path))

    assert result["source"] == "json-summary"
    assert result["layers"]["core"] == 90.0  # (9+9)/(10+10)
    assert result["layers"]["adapters"] == 50.0
    assert result["layers"]["entrypoints"] == 20.0


def test_parse_coverage_by_layer_absent_is_graceful(tmp_path: Path) -> None:
    result = _parse_coverage_by_layer(str(tmp_path))

    assert result["source"] == "absent"
    assert result["layers"] == {}


def test_scoring_v1_reproduces_legacy_saturation() -> None:
    # Legacy ceiling: the bonus completes a 99 base straight to 100% (the behaviour
    # historical runs were scored with).
    summary = _compute_final_score_summary(_audit_db_base_99(bonus=5), "v1")

    assert summary["final_percentage"] == 100


def test_scoring_v2_has_dedicated_cost_bucket() -> None:
    summary = _compute_final_score_summary(_audit_db_base_99(bonus=0), "v2")
    assert "cost" in summary["bucket_scores"]
    assert summary["bucket_scores"]["cost"]["weight"] == 12
    assert round(summary["base_score"], 1) == 99.0  # incl. the maxed cost bucket


def test_normalize_model_id_maps_known_families() -> None:
    assert _normalize_model_id("claude-fable-5") == "claude-fable"
    assert _normalize_model_id("claude-opus-4-8") == "claude-opus"
    assert _normalize_model_id("claude-sonnet-4-6") == "claude-sonnet"
    assert _normalize_model_id("GPT5.5-medium") == "gpt-5.5"
    assert _normalize_model_id("gpt-5") == "gpt-5"
    assert _normalize_model_id("AGY_GEMINI_3.5-flash") == "gemini-flash"
    assert _normalize_model_id("gemini-2.5-pro") == "gemini-pro"
    assert _normalize_model_id("codex") == "gpt-5"  # Codex CLI → GPT-5 tier
    assert _normalize_model_id("gpt-5-codex") == "gpt-5"
    assert _normalize_model_id("some-unknown-model") is None
    assert _normalize_model_id(None) is None


def test_compute_session_cost_prices_known_model() -> None:
    trace = {
        "total_input_tokens": 100_000,
        "total_output_tokens": 50_000,
        "total_cached_input_tokens": 0,
    }
    cost = _compute_session_cost(trace, "claude-opus-4-8")
    assert cost["priced"] is True
    assert cost["total_tokens"] == 150_000
    # 0.1M*5 + 0.05M*25 = 0.5 + 1.25
    assert cost["cost_usd"] == 1.75


def test_compute_session_cost_cached_billed_cheaper() -> None:
    # 600k input INCLUDING 200k cached, 90k output, opus pricing → cached billed at the
    # cheaper cached rate, the remaining 400k input at the full rate.
    trace = {
        "total_input_tokens": 600_000,
        "total_output_tokens": 90_000,
        "total_cached_input_tokens": 200_000,
    }
    cost = _compute_session_cost(trace, "claude-opus-4-8")
    # 0.4M*5 + 0.2M*0.5 + 0.09M*25 = 2.0 + 0.1 + 2.25
    assert cost["cost_usd"] == 4.35
    assert cost["total_tokens"] == 690_000


def test_compute_session_cost_unpriced_model_keeps_tokens() -> None:
    trace = {"total_input_tokens": 80_000, "total_output_tokens": 20_000}
    cost = _compute_session_cost(trace, "mystery-model-x")
    assert cost["priced"] is False
    assert cost["cost_usd"] is None
    assert cost["total_tokens"] == 100_000


def test_compute_session_cost_no_tokens_is_none() -> None:
    cost = _compute_session_cost({}, "claude-opus-4-8")
    assert cost["total_tokens"] is None
    assert cost["cost_usd"] is None


def _make_fake_graphql_server(secure: bool):
    """Stateful in-memory GraphQL server for AuthTester. ``secure`` toggles JWT
    verification and per-user isolation so tests can assert discrimination."""
    state = {"users": {}, "tasks": [], "n": 0}

    def post(query, token=None):
        if "register(" in query and 'password: "123"' in query:
            if secure:
                return {
                    "errors": [
                        {"message": "weak password", "extensions": {"code": "BAD_USER_INPUT"}}
                    ]
                }
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
            return {
                "errors": [
                    {"message": "unauthenticated", "extensions": {"code": "UNAUTHENTICATED"}}
                ]
            }
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


def test_precreate_bind_mount_dirs_creates_only_in_tree_binds(tmp_path: Path) -> None:
    deliverable = tmp_path / "deliverable"
    deliverable.mkdir()
    (deliverable / "docker-compose.yml").write_text(
        "services:\n"
        "  api:\n"
        "    build: .\n"
        "    volumes:\n"
        "      - ./coverage:/app/coverage\n"  # in-tree bind -> created
        "      - mydata:/data\n"  # named volume -> skipped
        "      - /etc/hosts:/etc/hosts:ro\n"  # out-of-tree -> skipped
        "volumes:\n"
        "  mydata:\n",
        encoding="utf-8",
    )
    created = precreate_bind_mount_dirs(str(deliverable))

    assert (deliverable / "coverage").is_dir()
    assert [Path(p).name for p in created] == ["coverage"]
    assert not (deliverable / "mydata").exists()


def test_precreate_bind_mount_dirs_long_syntax(tmp_path: Path) -> None:
    deliverable = tmp_path / "deliverable"
    deliverable.mkdir()
    (deliverable / "docker-compose.yml").write_text(
        "services:\n"
        "  api:\n"
        "    volumes:\n"
        "      - type: bind\n"
        "        source: ./reports\n"
        "        target: /app/reports\n",
        encoding="utf-8",
    )
    precreate_bind_mount_dirs(str(deliverable))
    assert (deliverable / "reports").is_dir()


def test_precreate_bind_mount_dirs_noop_without_compose(tmp_path: Path) -> None:
    deliverable = tmp_path / "deliverable"
    deliverable.mkdir()
    assert precreate_bind_mount_dirs(str(deliverable)) == []


# --------------------------------------------------------------------------- #
# Revue 2026-09-22 — non-régressions
# --------------------------------------------------------------------------- #
_JEST_OUTPUT = """
PASS src/core/a.test.ts
Test Suites: 28 passed, 28 total
Tests:       241 passed, 241 total
Snapshots:   0 total
"""


def test_parse_test_results_reads_tests_line_not_suites() -> None:
    from main import _parse_test_results

    assert _parse_test_results(_JEST_OUTPUT) == {"passed": 241, "failed": 0, "total": 241}
    mixed = (
        "Test Suites: 1 failed, 11 passed, 12 total\nTests:       2 failed, 80 passed, 82 total\n"
    )
    assert _parse_test_results(mixed) == {"passed": 80, "failed": 2, "total": 82}
    # No "Tests:" line (other runner): legacy first-occurrence behaviour is kept.
    assert _parse_test_results("5 passed, 5 total")["passed"] == 5


def test_normalize_model_id_prices_successors_separately() -> None:
    assert _normalize_model_id("claude-opus-5-5") == "claude-opus-5-5"
    assert _normalize_model_id("Claude Opus 5.5") == "claude-opus-5-5"
    assert _normalize_model_id("claude-opus-5[1m]") == "claude-opus"
    assert _normalize_model_id("claude-fable-5-1") == "claude-fable-5-1"
    assert _normalize_model_id("claude-fable-5") == "claude-fable"


def test_compute_session_cost_opus_5_5_rates() -> None:
    trace = {
        "total_input_tokens": 6_800_000,
        "total_output_tokens": 158_000,
        "total_cached_input_tokens": 5_900_000,
    }
    # 0.9M*4 + 5.9M*0.20 + 0.158M*20 = 3.6 + 1.18 + 3.16
    assert _compute_session_cost(trace, "claude-opus-5-5")["cost_usd"] == 7.94
    # Same tokens at Opus 5 rates stay unchanged (historical comparability).
    assert _compute_session_cost(trace, "claude-opus-5[1m]")["cost_usd"] == 11.4


def _run_analyze_with_docker_start(tmp_path: Path, monkeypatch, docker_status: str) -> dict:
    project = tmp_path / "deliverable"
    project.mkdir()
    out_dir = tmp_path / "cr_audits"
    monkeypatch.setenv("HEXA_AUDIT_OUTPUT_DIR", str(out_dir))
    with (
        patch(
            "main.MakefileRunner.run_target",
            return_value={"status": "OK", "output": "", "error": "", "exit_code": 0},
        ),
        patch(
            "main.DockerOrchestrator.start",
            return_value={"status": docker_status, "error": "GraphQL endpoint not healthy"},
        ),
        patch("main.DockerOrchestrator.stop", return_value={"status": "OK"}),
        patch("main.NpmAuditChecker.audit", return_value={"status": "SKIPPED"}),
        patch("main.Environment.get_template") as get_template,
    ):
        get_template.return_value.render.return_value = "report"
        analyze.callback(str(project), False, False, False)
    return json.loads(next(out_dir.glob("*.json")).read_text(encoding="utf-8"))


def test_runtime_not_started_caps_score_like_a_failed_e2e(tmp_path: Path, monkeypatch) -> None:
    audit = _run_analyze_with_docker_start(tmp_path, monkeypatch, "KO")
    cap_ids = [c["id"] for c in audit["summary"]["score_caps"]]
    assert cap_ids == ["runtime_not_started"]
    assert audit["summary"]["percentage_net"] <= 40
    # compose_ports / makefile_teardown artifacts survive the final artifacts merge.
    assert "compose_ports" in audit["artifacts"]
    assert "makefile_teardown" in audit["artifacts"]


def test_skip_dynamic_is_not_capped(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "deliverable"
    project.mkdir()
    out_dir = tmp_path / "cr_audits"
    monkeypatch.setenv("HEXA_AUDIT_OUTPUT_DIR", str(out_dir))
    with (
        patch(
            "main.MakefileRunner.run_target",
            return_value={"status": "OK", "output": "", "error": "", "exit_code": 0},
        ),
        patch("main.Environment.get_template") as get_template,
    ):
        get_template.return_value.render.return_value = "report"
        analyze.callback(str(project), True, False, False)
    audit = json.loads(next(out_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert audit["summary"]["score_caps"] == []


def test_auth_forged_tokens_need_positive_control() -> None:
    """A server whose `tasks` query fails for everyone must not score as rejecting
    alg=none / foreign signatures, nor pass the weak-password probe when register is
    broken."""

    def broken(query, token=None):
        if "register(" in query or "login(" in query:
            return {"errors": [{"message": "internal error"}]}
        return {"errors": [{"message": "Cannot query field tasks"}]}

    tester = AuthTester("http://example.test/graphql")
    with patch.object(tester, "_post", side_effect=broken):
        results = {r["step"]: r["success"] for r in tester.run_scenario()}
    assert results["Auth: Token alg=none rejeté"] is False
    assert results["Auth: Signature étrangère rejetée"] is False
    assert results["Auth: Mot de passe faible refusé"] is False


def test_adversarial_probes_require_graphql_error_evidence() -> None:
    tester = E2EFunctionalTester("http://example.test/graphql", token="pre.baked.token0123456789")
    with patch.object(tester, "_post", return_value={"_request_failed": True}):
        results = {r["step"]: r["success"] for r in tester.run_adversarial_scenario()}
    assert results["Adversarial: Dépendance inexistante rejetée"] is False


def test_adversarial_ghost_dependency_uses_well_formed_ids() -> None:
    """A Mongo engine that only rejects malformed ObjectIds (cast error) but never
    checks existence must fail the ghost-dependency probe."""
    state = {"n": 0}

    def cast_only(query):
        block = re.search(r"dependsOn:\s*\[([^\]]*)\]", query)
        deps = re.findall(r'"([^"]+)"', block.group(1)) if block else []
        if any(not re.fullmatch(r"[0-9a-f]{24}", d) for d in deps):
            return {"errors": [{"message": "Cast to ObjectId failed"}]}
        state["n"] += 1
        return {"data": {"createTask": {"id": f"{state['n']:024x}"}}}

    tester = E2EFunctionalTester("http://example.test/graphql", token="pre.baked.token0123456789")
    with patch.object(tester, "_post", side_effect=cast_only):
        results = {r["step"]: r for r in tester.run_adversarial_scenario()}
    assert results["Adversarial: Dépendance inexistante rejetée"]["success"] is False
