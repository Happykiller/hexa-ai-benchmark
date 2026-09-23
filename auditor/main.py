import functools
import json
import logging
import os
import re
import subprocess
from datetime import datetime
from typing import Any

import click
from challenges import DEFAULT_PROFILE
from engine import (  # noqa: F401 — ré-exports : tests et scripts/session_usage.py
    TraceabilityValidator,
    _aggregate_status,
    _append_indicator,
    _append_scored_indicator_from_config,
    _build_trace_metrics,
    _compute_bonus_malus_adjustment,
    _compute_bucket_score,
    _compute_final_score_summary,
    _compute_score_caps,
    _compute_session_cost,
    _fibonacci,
    _finalize_audit_db,
    _first_non_empty,
    _format_number,
    _md_cell,
    _normalize_model_id,
    _parse_iso_datetime,
    _score_from_bands,
    _to_float,
    emit_cost_indicators,
    emit_trace_indicators,
)
from jinja2 import Environment, FileSystemLoader
from modules.dynamic_analysis import (
    AuthTester,
    DockerOrchestrator,
    E2EFunctionalTester,
    MakefileRunner,
    PerformanceBenchmarker,
    precreate_bind_mount_dirs,
)
from modules.static_analysis import (
    CodeSmellAnalyzer,
    ProjectStatsAnalyzer,
)
from modules.supply_chain import (
    ComposePortsChecker,
    MakefileTeardownChecker,
    NpmAuditChecker,
    SecretsScanner,
)
from rich.console import Console
from rich.table import Table
from scoring_config import (
    PRICING_UPDATED,
    SCORING_DEFAULT_VERSION,
    TECHNICAL_STATS_SCORING_CONFIG,
)

console = Console()


def _log(message: str) -> None:
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] {message}")


def _parse_test_results(output: str) -> dict[str, int]:
    """Parses Jest-style test output for passed/failed/total counts.

    Jest prints a "Test Suites:" summary line *before* the "Tests:" one; counts are read
    from the "Tests:" line (test cases), never from the suites line — otherwise the
    number of files is taken for the number of executed tests. Falls back to the first
    occurrence anywhere for runners that print no "Tests:" line."""
    res = {"passed": 0, "failed": 0, "total": 0}

    # Last "Tests:" line wins (watch/retry output may print several summaries).
    tests_lines = re.findall(r"^\s*Tests:\s*(.+)$", output, re.MULTILINE)
    scope = tests_lines[-1] if tests_lines else output

    # Matches "5 passed", "1 failed", "6 total" independently to be robust
    passed_match = re.search(r"(\d+)\s+passed", scope)
    if passed_match:
        res["passed"] = int(passed_match.group(1))

    failed_match = re.search(r"(\d+)\s+failed", scope)
    if failed_match:
        res["failed"] = int(failed_match.group(1))

    total_match = re.search(r"(\d+)\s+total", scope)
    if total_match:
        res["total"] = int(total_match.group(1))

    return res


def _parse_coverage_results(output: str) -> dict[str, Any]:
    """Parses Jest --coverage output for global line/statement coverage percentage."""
    # Istanbul text table: "All files | 78.57 | ..."
    table = re.search(r"All files\s*\|\s*([\d.]+)", output)
    if table:
        return {"coverage_pct": float(table.group(1)), "source": "table"}
    # Istanbul summary: "Lines        : 78.57% ( 22/28 )"
    lines = re.search(r"Lines\s*[:\|]\s*([\d.]+)\s*%", output, re.IGNORECASE)
    if lines:
        return {"coverage_pct": float(lines.group(1)), "source": "summary_lines"}
    # Statements fallback
    stmts = re.search(r"Statements\s*[:\|]\s*([\d.]+)\s*%", output, re.IGNORECASE)
    if stmts:
        return {"coverage_pct": float(stmts.group(1)), "source": "summary_stmts"}
    return {"coverage_pct": None, "source": "not_found"}


def _parse_coverage_by_layer(target_path: str) -> dict[str, Any]:
    """Aggregate Istanbul line coverage per hexagonal layer from
    coverage/coverage-summary.json (the json-summary reporter). Returns per-layer pct,
    or an empty map with a ``source`` reason when the file is absent/unreadable — the
    caller then records the per-layer indicators as informational (no penalty)."""
    summary_path = os.path.join(target_path, "coverage", "coverage-summary.json")
    if not os.path.isfile(summary_path):
        return {"source": "absent", "layers": {}}
    try:
        with open(summary_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"source": "unreadable", "layers": {}}
    if not isinstance(data, dict):
        return {"source": "unreadable", "layers": {}}

    agg = {"core": [0, 0], "adapters": [0, 0], "entrypoints": [0, 0]}  # [covered, total]
    for key, metrics in data.items():
        if key == "total" or not isinstance(metrics, dict):
            continue
        norm = key.replace("\\", "/")
        for layer, bucket in agg.items():
            if f"/{layer}/" in norm:
                lines = metrics.get("lines", {}) if isinstance(metrics.get("lines"), dict) else {}
                bucket[0] += int(lines.get("covered", 0) or 0)
                bucket[1] += int(lines.get("total", 0) or 0)
                break

    layers = {
        layer: (round(covered / total * 100, 2) if total else None)
        for layer, (covered, total) in agg.items()
    }
    return {"source": "json-summary", "layers": layers}


def _functional_e2e_failed(e2e_results: list[dict[str, Any]]) -> bool:
    return any(not bool(step.get("success")) for step in e2e_results)


def _make_status_line(result: dict[str, Any]) -> str:
    exit_code = result.get("exit_code")
    if exit_code is not None:
        message = f"exit_code={exit_code}"
    else:
        message = result.get("status", "UNKNOWN")
    extra = _first_non_empty(result.get("error"), result.get("details"))
    return f"{message}; {extra}" if extra else message


@click.group()
def cli() -> None:
    """AI Agent Deliverable Auditor CLI"""
    # Opt-in diagnostics: set HEXA_AUDIT_LOG_LEVEL=DEBUG to surface the module-level
    # debug logs (Docker/E2E/auth request failures) when a run needs investigating.
    _log_level = os.environ.get("HEXA_AUDIT_LOG_LEVEL")
    if _log_level:
        logging.basicConfig(level=_log_level.upper(), format="%(levelname)s %(name)s: %(message)s")


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--skip-dynamic", is_flag=True, help="Skip docker and dynamic tests")
@click.option(
    "--force-dynamic",
    is_flag=True,
    help="Run make test, Docker, E2E and perf even if make build fails",
)
@click.option("--fresh-docker", is_flag=True, help="Run docker compose down -v before make start")
@click.option(
    "--scoring",
    type=click.Choice(["v1", "v2"]),
    default=SCORING_DEFAULT_VERSION,
    show_default=True,
    help="Final-score ceiling rule: v2 reserves 100%% for a flawless base; v1 reproduces legacy scores",
)
def analyze(
    path: str,
    skip_dynamic: bool,
    force_dynamic: bool,
    fresh_docker: bool,
    scoring: str = SCORING_DEFAULT_VERSION,
) -> None:
    """Analyze a deliverable at the given PATH"""
    if skip_dynamic and force_dynamic:
        raise click.UsageError("--skip-dynamic and --force-dynamic cannot be used together")

    _log(f"[bold blue]Starting Full Audit for:[/bold blue] {path}")
    audit_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    audit_db: dict[str, Any] = {
        "meta": {
            "target_path": path,
            "audit_started_at": audit_started_at,
            "audit_finished_at": None,
            "skip_dynamic": skip_dynamic,
            "force_dynamic": force_dynamic,
            "fresh_docker": fresh_docker,
            "scoring_model": "indicator_fibonacci_v2",
            "scoring_version": scoring,
        },
        "summary": {},
        "phases": [],
        "indicators": [],
        "points": [],
    }
    audit_db["meta"]["score_cap_reasons"] = []

    profile = DEFAULT_PROFILE
    make = MakefileRunner(path)
    op_results: dict[str, dict[str, Any]] = {}

    expected_e2e_steps = list(profile.e2e_step_names)
    auth_step_weights: dict[str, int] = dict(profile.auth_step_weights)
    adversarial_step_weights: dict[str, int] = dict(profile.adversarial_step_weights)

    # Pre-create docker-compose bind-mount host dirs (owned by the audit user) so the
    # Docker daemon doesn't auto-create them as root and break the build context — a false
    # "make build failed" that otherwise caps the whole run at 40%.
    _precreated = precreate_bind_mount_dirs(path)
    if _precreated:
        _log(f"Pré-création des bind-mounts: {', '.join(os.path.basename(p) for p in _precreated)}")

    # 1. Setup
    _log("Running make setup...")
    op_results["setup"] = make.run_target("setup")
    _append_indicator(
        audit_db,
        1,
        "Opérationnalité",
        1,
        "Exécution des cibles make & Docker",
        "make setup",
        op_results["setup"]["status"] == "OK",
        _make_status_line(op_results["setup"]),
        details=op_results["setup"],
        weight=1,
    )

    # 2. Lint, Build, Test
    orchestrator = DockerOrchestrator(path, endpoint=profile.graphql_endpoint)
    docker_start = {"status": "SKIPPED", "details": "dynamic phase not started"}
    exposed_containers = {"containers": [], "status": "SKIPPED"}

    _log("Running make lint...")
    op_results["lint"] = make.run_target("lint")
    _append_indicator(
        audit_db,
        1,
        "Opérationnalité",
        1,
        "Exécution des cibles make & Docker",
        "make lint",
        op_results["lint"]["status"] == "OK",
        _make_status_line(op_results["lint"]),
        details=op_results["lint"],
        weight=5,
    )

    _log("Running make build...")
    op_results["build"] = make.run_target("build")
    _append_indicator(
        audit_db,
        1,
        "Opérationnalité",
        1,
        "Exécution des cibles make & Docker",
        "make build",
        op_results["build"]["status"] == "OK",
        _make_status_line(op_results["build"]),
        details=op_results["build"],
        weight=10,
    )

    is_operational = op_results["build"]["status"] == "OK"
    should_run_dynamic = not skip_dynamic and (is_operational or force_dynamic)

    if is_operational or force_dynamic:
        if force_dynamic and not is_operational:
            _log("make build failed; --force-dynamic is set, continuing with make test...")
        else:
            _log("Running make test...")
        op_results["test"] = make.run_target("test")
    else:
        op_results["test"] = {
            "status": "SKIPPED",
            "details": "make build failed; test phase not executed",
        }
    _append_indicator(
        audit_db,
        1,
        "Opérationnalité",
        1,
        "Exécution des cibles make & Docker",
        "make test",
        op_results["test"]["status"] == "OK",
        _make_status_line(op_results["test"]),
        status=op_results["test"]["status"] if op_results["test"]["status"] == "SKIPPED" else None,
        details=op_results["test"],
        weight=10,
    )

    if should_run_dynamic:
        if force_dynamic and not is_operational:
            _log(
                "make build failed; --force-dynamic is set, starting Docker infrastructure anyway..."
            )
        else:
            _log("Starting Docker infrastructure (make start)...")
        if fresh_docker:
            _log("Fresh Docker mode enabled: running docker compose down -v before make start...")
        docker_start = orchestrator.start(fresh=fresh_docker)
    elif skip_dynamic:
        docker_start = {"status": "SKIPPED", "details": "dynamic phase skipped"}
    else:
        docker_start = {
            "status": "SKIPPED",
            "details": "make build failed; dynamic phase not executed",
        }

    _append_indicator(
        audit_db,
        1,
        "Opérationnalité",
        1,
        "Exécution des cibles make & Docker",
        "make start",
        docker_start["status"] == "OK",
        _make_status_line(docker_start),
        status=docker_start["status"] if docker_start["status"] == "SKIPPED" else None,
        details=docker_start,
        weight=10,
    )

    if docker_start["status"] == "OK":
        _log("Inspecting active Docker containers...")
        exposed_containers = orchestrator.inspect_exposed_containers()
        containers_list = exposed_containers.get("containers", [])
        if not containers_list:
            _append_indicator(
                audit_db,
                1,
                "Opérationnalité",
                1,
                "Exécution des cibles make & Docker",
                "Conteneurs actifs",
                False,
                "Aucun conteneur détecté",
                details=exposed_containers,
                weight=2,
            )
        for container in containers_list:
            _append_indicator(
                audit_db,
                1,
                "Opérationnalité",
                1,
                "Exécution des cibles make & Docker",
                f"Conteneur : {container['name']}",
                container["state"] in ("running", "up", "active"),
                f"state={container['state']}, status={container['status']}",
                details=container,
                weight=2,
            )

    # Detect version obsolete in command outputs (flexible regex)
    version_obsolete_count = 0
    obsolete_pattern = re.compile(r"attribute .*version.* is obsolete", re.IGNORECASE)
    for res in list(op_results.values()) + [docker_start]:
        out = (
            str(res.get("output", ""))
            + " "
            + str(res.get("error", ""))
            + " "
            + str(res.get("stderr", ""))
        )
        version_obsolete_count += len(obsolete_pattern.findall(out))

    traceability = TraceabilityValidator(path).validate()
    stats = ProjectStatsAnalyzer(path).analyze()
    smells = CodeSmellAnalyzer(path).analyze()
    trace_metrics = _build_trace_metrics(traceability)
    # hexagonal / quality / readme / auth_static / injection / dual_persistence are
    # run and scored via the declarative registry (profile.static_checkers) below.

    # Parse test execution results early
    test_out = ""
    if "test" in op_results:
        test_out = str(op_results["test"].get("output", "")) + str(
            op_results["test"].get("error", "")
        )
    test_results = _parse_test_results(test_out)
    coverage_data = _parse_coverage_results(test_out)
    coverage_by_layer = _parse_coverage_by_layer(path)
    stats["execution_test_passed"] = test_results.get("passed", 0)
    stats["execution_test_failed"] = test_results.get("failed", 0)
    stats["execution_test_total"] = test_results.get("total", 0)
    stats["coverage_pct"] = coverage_data.get("coverage_pct")

    # Add Docker Obsolete Malus as FIRST malus to ensure -1pt (rank 1)
    smells.setdefault("all_maluses", []).insert(
        0,
        {
            "id": "docker_version_obsolete",
            "reason": "Docker version attribute is obsolete",
            "status": "DETECTE" if version_obsolete_count > 0 else "NON_DETECTE",
            "count": version_obsolete_count,
            "detail": f"obsolete_detected_count={version_obsolete_count}",
        },
    )

    # Anti-gaming maluses derived from test quality vs declared test files.
    _assertion_ratio = stats.get("assertion_ratio", 0.0)
    _test_files = stats.get("total_tests", 0)
    _exec_cases = stats.get("execution_test_total", 0)
    smells["all_maluses"].append(
        {
            "id": "tests_without_assertions",
            "reason": "Fichiers de test sans assertion réelle",
            "status": "DETECTE" if (_test_files >= 5 and _assertion_ratio < 0.5) else "NON_DETECTE",
            "count": _test_files,
            "detail": f"assertion_ratio={_assertion_ratio}, test_files={_test_files}",
        }
    )
    smells["all_maluses"].append(
        {
            "id": "tests_declared_not_executed",
            "reason": "Plus de fichiers de test que de cas réellement exécutés (padding)",
            "status": "DETECTE"
            if (_test_files >= 8 and 0 < _exec_cases < _test_files)
            else "NON_DETECTE",
            "count": _test_files,
            "detail": f"executed_cases={_exec_cases}, test_files={_test_files}",
        }
    )

    # Supply-chain / secrets maluses (Phase D). Secrets scan is static (always run);
    # npm audit needs the network, so it is skipped with --skip-dynamic.
    secrets_res = SecretsScanner(path).scan()
    smells["all_maluses"].append(
        {
            "id": "committed_secrets",
            "reason": "Secrets / clés / .env commités dans le dépôt",
            "status": secrets_res.get("status", "NON_DETECTE"),
            "count": secrets_res.get("count", 0),
            "detail": secrets_res.get("detail", ""),
        }
    )
    npm_res = (
        {"status": "SKIPPED", "detail": "--skip-dynamic"}
        if skip_dynamic
        else NpmAuditChecker(path).audit()
    )
    smells["all_maluses"].append(
        {
            "id": "npm_vulnerabilities",
            "reason": "Vulnérabilités npm (high/critical)",
            "status": npm_res.get("status", "SKIPPED"),
            "count": npm_res.get("critical", 0) + npm_res.get("high", 0),
            "detail": npm_res.get("detail", ""),
        }
    )

    performance = {"avg_latency_ms": 0, "p95_ms": 0, "error_rate": 0}
    e2e_results: list[dict[str, Any]] = []
    auth_e2e_results: list[dict[str, Any]] = []
    auth_token: str | None = None

    # Step 1-2: Validation fonctionnelle E2E
    if docker_start["status"] == "OK":
        endpoint = profile.graphql_endpoint
        try:
            _log("Running Auth scenario...")
            auth_tester = AuthTester(endpoint)
            auth_e2e_results = auth_tester.run_scenario()
            auth_token = auth_tester.token

            e2e = E2EFunctionalTester(endpoint, token=auth_token)
            perf = PerformanceBenchmarker(endpoint, token=auth_token)

            _log("Running E2E Scenario...")
            e2e_results = e2e.run_scenario()
            executed_steps = [r["step"] for r in e2e_results]
            for e2e_step in e2e_results:
                _append_indicator(
                    audit_db,
                    1,
                    "Opérationnalité",
                    2,
                    "Validation fonctionnelle E2E",
                    e2e_step["step"],
                    bool(e2e_step.get("success")),
                    _first_non_empty(e2e_step.get("error"), "validated"),
                    details=e2e_step,
                    weight=5,
                )

            for step_name in expected_e2e_steps:
                if step_name not in executed_steps:
                    _append_indicator(
                        audit_db,
                        1,
                        "Opérationnalité",
                        2,
                        "Validation fonctionnelle E2E",
                        step_name,
                        False,
                        "Step not reached due to previous failure",
                        status="SKIPPED",
                        weight=5,
                    )

            _log("Running Performance Benchmark...")
            performance = perf.run_benchmark("{ tasks { id } }", {}, iterations=50)
            perf_success = (
                performance.get("avg_latency_ms", 0) > 0 and performance.get("error_rate", 100) <= 5
            )
            _append_indicator(
                audit_db,
                1,
                "Opérationnalité",
                2,
                "Validation fonctionnelle E2E",
                "Benchmark API",
                perf_success,
                (
                    f"avg_latency_ms={round(performance.get('avg_latency_ms', 0), 2)}, "
                    f"p95_ms={round(performance.get('p95_ms', 0), 2)}, "
                    f"error_rate={round(performance.get('error_rate', 0), 2)}"
                ),
                details=performance,
                weight=5,
            )
            executed_auth_steps = [r["step"] for r in auth_e2e_results]
            for auth_step in auth_e2e_results:
                _append_indicator(
                    audit_db,
                    1,
                    "Opérationnalité",
                    4,
                    "Validation sécurité E2E",
                    auth_step["step"],
                    bool(auth_step.get("success")),
                    _first_non_empty(auth_step.get("error"), "validated"),
                    details=auth_step,
                    weight=auth_step_weights.get(auth_step["step"], 5),
                )
            for step_name, w in auth_step_weights.items():
                if step_name not in executed_auth_steps:
                    _append_indicator(
                        audit_db,
                        1,
                        "Opérationnalité",
                        4,
                        "Validation sécurité E2E",
                        step_name,
                        False,
                        "Step not reached",
                        status="SKIPPED",
                        weight=w,
                    )

            # Step 1-5: Adversarial business-logic robustness (de-saturation). Kept
            # separate from the functional E2E so an edge-case miss never caps at 40%.
            _log("Running Adversarial Scenario...")
            adversarial_results = e2e.run_adversarial_scenario()
            executed_adv_steps = [r["step"] for r in adversarial_results]
            for adv_step in adversarial_results:
                _append_indicator(
                    audit_db,
                    1,
                    "Opérationnalité",
                    5,
                    "Robustesse métier (E2E adversarial)",
                    adv_step["step"],
                    bool(adv_step.get("success")),
                    _first_non_empty(adv_step.get("error"), "validated"),
                    details=adv_step,
                    weight=adversarial_step_weights.get(adv_step["step"], 5),
                )
            for step_name, w in adversarial_step_weights.items():
                if step_name not in executed_adv_steps:
                    _append_indicator(
                        audit_db,
                        1,
                        "Opérationnalité",
                        5,
                        "Robustesse métier (E2E adversarial)",
                        step_name,
                        False,
                        "Step not reached",
                        status="SKIPPED",
                        weight=w,
                    )
        finally:
            orchestrator.stop()
    else:
        # A failed `make start` may still have left partial containers up — always tear
        # them down so the audit never leaks a running stack (clean environment).
        if docker_start["status"] == "KO":
            _log("make start failed; tearing down any partial containers...")
            orchestrator.stop()

        # Fallback for failed/skipped docker start
        reason = docker_start.get("error", "runtime not started")
        if skip_dynamic:
            reason = "dynamic phase skipped"
        elif not is_operational and not force_dynamic:
            reason = "make build failed; dynamic phase not executed"

        for step_name in expected_e2e_steps:
            _append_indicator(
                audit_db,
                1,
                "Opérationnalité",
                2,
                "Validation fonctionnelle E2E",
                step_name,
                False,
                reason,
                status="SKIPPED",
                weight=5,
            )
        _append_indicator(
            audit_db,
            1,
            "Opérationnalité",
            2,
            "Validation fonctionnelle E2E",
            "Benchmark API",
            False,
            reason,
            status="SKIPPED",
            details=performance,
            weight=5,
        )
        for step_name, w in auth_step_weights.items():
            _append_indicator(
                audit_db,
                1,
                "Opérationnalité",
                4,
                "Validation sécurité E2E",
                step_name,
                False,
                reason,
                status="SKIPPED",
                weight=w,
            )
        for step_name, w in adversarial_step_weights.items():
            _append_indicator(
                audit_db,
                1,
                "Opérationnalité",
                5,
                "Robustesse métier (E2E adversarial)",
                step_name,
                False,
                reason,
                status="SKIPPED",
                weight=w,
            )

    # Step 1-3: Résultats détaillés des tests unitaires
    passed_count = stats.get("execution_test_passed", 0)
    failed_count = stats.get("execution_test_failed", 0)

    # Scoring logic for Passed Tests (Target 21 points)
    # 0..1=1pt (ratio 0.05), 2..5=3pts (0.14), 6..13=10pts (0.47), 14..21=21pts (1.0)
    passed_ratio = 0.0
    if passed_count >= 14:
        passed_ratio = 1.0
    elif passed_count >= 6:
        passed_ratio = 0.47
    elif passed_count >= 2:
        passed_ratio = 0.14
    elif passed_count >= 0:
        passed_ratio = 0.05

    # Anti-gaming: passing tests only count fully when test files actually assert
    # something. Tests stuffed without assertions are heavily discounted.
    assertion_ratio = stats.get("assertion_ratio", 0.0)
    if assertion_ratio >= 0.6:
        assertion_quality = 1.0
    elif assertion_ratio >= 0.3:
        assertion_quality = 0.6
    else:
        assertion_quality = 0.3
    passed_ratio = round(passed_ratio * assertion_quality, 4)

    _append_indicator(
        audit_db,
        1,
        "Opérationnalité",
        3,
        "Résultats des tests unitaires",
        "Tests PASS",
        passed_count > 0,
        f"count={passed_count}, assertion_ratio={assertion_ratio}, quality_factor={assertion_quality}",
        score_ratio=passed_ratio,
        weight=21,
    )

    # Scoring logic for Failed Tests (Malus up to -21 points)
    failed_ratio = 0.0
    if failed_count >= 14:
        failed_ratio = 1.0
    elif failed_count >= 6:
        failed_ratio = 0.47
    elif failed_count >= 2:
        failed_ratio = 0.14
    elif failed_count >= 1:
        failed_ratio = 0.05

    _append_indicator(
        audit_db,
        1,
        "Opérationnalité",
        3,
        "Résultats des tests unitaires",
        "Tests FAIL",
        failed_count > 0,
        f"count={failed_count}",
        polarity="negative",
        score_ratio=failed_ratio,
        weight=21,
    )

    # Coverage indicator — bands: ≥80%=100%, ≥60%=50%, else=0%
    cov_pct = coverage_data.get("coverage_pct")
    cov_ratio = 0.0
    if cov_pct is not None:
        if cov_pct >= 80.0:
            cov_ratio = 1.0
        elif cov_pct >= 60.0:
            cov_ratio = 0.5
    _append_indicator(
        audit_db,
        1,
        "Opérationnalité",
        3,
        "Résultats des tests unitaires",
        "Couverture de code (%)",
        cov_pct is not None and cov_pct >= 60.0,
        f"coverage={cov_pct}% (source={coverage_data.get('source')})"
        if cov_pct is not None
        else "non détectée — --coverage manquant ?",
        score_ratio=cov_ratio,
        weight=15,
    )

    # Coverage by layer (continuous): core must be tested harder than entrypoints. When
    # the json-summary reporter is absent the indicator is informational (kind=measured),
    # so a missing report never penalises — it only adds resolution when present.
    cov_layers = coverage_by_layer.get("layers", {})
    for _layer, _target, _w in (
        ("core", 85.0, 10),
        ("adapters", 60.0, 5),
        ("entrypoints", 40.0, 3),
    ):
        _pct = cov_layers.get(_layer)
        _name = f"Couverture {_layer}/ (cible ≥{int(_target)}%)"
        if _pct is None:
            _append_indicator(
                audit_db,
                1,
                "Opérationnalité",
                3,
                "Résultats des tests unitaires",
                _name,
                False,
                f"coverage-summary.json {coverage_by_layer.get('source')} — couche non mesurée",
                kind="measured",
                measured_value=None,
                details=coverage_by_layer,
            )
        else:
            _append_indicator(
                audit_db,
                1,
                "Opérationnalité",
                3,
                "Résultats des tests unitaires",
                _name,
                _pct >= _target,
                f"coverage_{_layer}={_pct}% (cible {int(_target)}%)",
                score_ratio=round(min(1.0, _pct / _target), 4),
                weight=_w,
                details=coverage_by_layer,
            )

    # docker-compose / Makefile deployment contract (static, always run, no Docker
    # needed): mongo/mysql published on the mandated NON-STANDARD host ports (no host
    # collision) and a Makefile teardown target (clean environment after the work).
    _compose_step = "Contrat docker-compose (ports & teardown)"
    if profile.db_port_contract:
        ports_res = ComposePortsChecker(path, profile.db_port_contract).check()
        audit_db.setdefault("artifacts", {})["compose_ports"] = ports_res
        for label, info in ports_res["services"].items():
            _append_indicator(
                audit_db,
                1,
                "Opérationnalité",
                6,
                _compose_step,
                f"{label} exposé sur le port hôte {info['expected_host']}",
                info["compliant"],
                info["detail"],
                weight=3,
                details=info,
            )
    teardown_res = MakefileTeardownChecker(path).check()
    audit_db.setdefault("artifacts", {})["makefile_teardown"] = teardown_res
    _append_indicator(
        audit_db,
        1,
        "Opérationnalité",
        6,
        _compose_step,
        "Cible Makefile de teardown (docker compose down)",
        teardown_res.get("has_teardown", False),
        teardown_res.get("detail", ""),
        weight=3,
        details=teardown_res,
    )

    # Static checkers run + scored via the declarative registry (challenges.py).
    # Order is defined by profile.static_checkers and reproduces indicator codes
    # 2-1-x .. 2-6-x exactly. Results are kept for the artifacts section below.
    static_results: dict[str, Any] = {}
    append_indicator = functools.partial(_append_indicator, audit_db)
    for spec in profile.static_checkers:
        result = spec.analyze(path)
        static_results[spec.id] = result
        spec.emit(result, append_indicator)

    if not is_operational:
        audit_db["meta"]["score_cap_reasons"].append(
            {
                "id": "build_failed",
                "max_percentage": 40,
                "reason": "make build failed",
            }
        )
    elif e2e_results and _functional_e2e_failed(e2e_results):
        audit_db["meta"]["score_cap_reasons"].append(
            {
                "id": "functional_e2e_failed",
                "max_percentage": 40,
                "reason": "functional E2E scenario failed",
            }
        )
    elif not skip_dynamic and docker_start["status"] != "OK":
        # A stack that never starts cannot pass the functional scenario: without this
        # cap, a deliverable whose `make start` fails would out-score one that starts
        # but misses a single E2E step (which is capped above). --skip-dynamic is an
        # operator choice, not a deliverable failure, so it stays uncapped.
        audit_db["meta"]["score_cap_reasons"].append(
            {
                "id": "runtime_not_started",
                "max_percentage": 40,
                "reason": "make start / GraphQL endpoint not healthy: functional E2E not executed",
            }
        )

    emit_trace_indicators(audit_db, traceability, trace_metrics)

    # Phase 6 — Cost pillar (scoring v2), see engine/cost.py.
    audit_db["meta"]["cost"] = emit_cost_indicators(audit_db, trace_metrics)

    for bonus in smells.get("all_bonuses", []):
        _append_indicator(
            audit_db,
            4,
            "Bonus / Malus",
            1,
            "Initiatives détectées",
            bonus.get("reason", "Bonus"),
            bonus.get("status") == "OK",
            f"detected={bonus.get('status') == 'OK'}",
            details=bonus,
        )

    for malus in smells.get("all_maluses", []):
        m_weight = 5
        if malus.get("id") == "docker_version_obsolete":
            m_weight = 1

        _append_indicator(
            audit_db,
            4,
            "Bonus / Malus",
            2,
            "Malus détectés",
            malus.get("reason", "Malus"),
            malus.get("status") == "DETECTE",
            malus.get("detail", malus.get("status", "INCONNU")),
            polarity="negative",
            status=malus.get("status"),
            details=malus,
            weight=m_weight,
        )

    for metric_key, config in TECHNICAL_STATS_SCORING_CONFIG.items():
        # Volume metrics are informational only — never scored, so file / test / LOC
        # padding cannot earn points (anti-gaming).
        _append_scored_indicator_from_config(
            audit_db,
            config,
            stats.get(metric_key),
            as_measured=True,
        )

    _finalize_audit_db(audit_db, scoring)
    audit_db["meta"]["audit_finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    audit_db["stats"] = stats

    try:
        tree_output = subprocess.run(
            [
                "tree",
                "-a",
                "-I",
                "node_modules|dist|build|tmp|.git|__pycache__|.pytest_cache|venv|.claude|coverage|tests",
                path,
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except Exception as e:
        tree_output = f"Erreur lors de l'exécution de tree: {e}"

    # Merge (not replace): compose_ports / makefile_teardown were stored earlier.
    audit_db.setdefault("artifacts", {}).update(
        {
            "make_targets": op_results,
            "docker_start": docker_start,
            "exposed_containers": exposed_containers,
            "e2e_results": e2e_results,
            "auth_e2e_results": auth_e2e_results,
            "auth_token_obtained": auth_token is not None,
            "performance": performance,
            "hexagonal": static_results.get("hexagonal", {}),
            "quality": static_results.get("quality", {}),
            "auth_static": static_results.get("auth_static", {}),
            "dual_persistence": static_results.get("dual_persistence", {}),
            "injection": static_results.get("injection", {}),
            "devex": static_results.get("devex", {}),
            "coverage": coverage_data,
            "traceability": traceability,
            "trace_metrics": trace_metrics,
            "smells": smells,
            "project_tree": tree_output,
        }
    )

    env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")))
    env.filters["md_cell"] = _md_cell
    template = env.get_template("report.md")

    report_content = template.render(audit_data=audit_db, stats=stats)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Output dir is overridable via HEXA_AUDIT_OUTPUT_DIR so tests (and one-off runs)
    # can isolate their artifacts. The default preserves the historical location the KB
    # builder scans — no effect on scoring.
    output_dir = os.environ.get("HEXA_AUDIT_OUTPUT_DIR") or os.path.join(repo_root, "cr_audits")
    os.makedirs(output_dir, exist_ok=True)

    safe_name = os.path.basename(path.rstrip("/"))
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_basename = f"cr_{safe_name}_{timestamp_str}"
    report_filename = f"{report_basename}.md"
    report_path = os.path.join(output_dir, report_filename)
    report_json_path = os.path.join(output_dir, f"{report_basename}.json")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(audit_db, f, indent=2, ensure_ascii=False)
    report_copy_path = os.path.join(path, f"audit_report_{timestamp_str}.md")
    with open(report_copy_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    summary = audit_db["summary"]
    bm = summary["bonus_malus_adjustment"]
    _eff_bonus = bm.get("effective_bonus")
    _bonus_shown = _eff_bonus if _eff_bonus is not None else bm.get("capped_adjustment", 0)
    console.print(
        f"[bold green]Audit Complete! Final: {summary['percentage_net']}%[/bold green] "
        f"[dim](base {summary['normalized_base_score']}/100 · "
        f"malus {bm.get('capped_malus', 0)} · bonus +{_bonus_shown} · "
        f"scoring {summary.get('scoring_version', SCORING_DEFAULT_VERSION)})[/dim]"
    )
    _cost_usd = summary.get("cost_usd")
    _eff = summary.get("cost_efficiency_pct_per_usd")
    _tokens = summary.get("total_tokens")
    if _cost_usd is not None:
        console.print(
            f"[bold cyan]Coût: ${_cost_usd}[/bold cyan] "
            f"[dim]({_tokens} tokens · valeur {_eff} pts/$ · prix {PRICING_UPDATED})[/dim]"
        )
    elif _tokens is not None:
        console.print(f"[dim]Coût non calculé (modèle non tarifé) · {_tokens} tokens[/dim]")
    else:
        console.print("[yellow]Coût non calculé : tokens absents de audit_trace.json[/yellow]")
    console.print(f"Detailed report saved to: [cyan]{report_path}[/cyan]")
    console.print(f"Audit data JSON saved to: [cyan]{report_json_path}[/cyan]")

    table = Table(title=f"Audit Results - {path}")
    table.add_column("Phase", style="cyan")
    table.add_column("Points (Earned/Possible)", style="green")

    for phase in audit_db["phases"]:
        table.add_row(
            phase["label"],
            f"{phase['raw_total']}/{phase['positive_points_possible']}",
        )

    table.add_section()
    table.add_row(
        "Base → Final",
        f"{summary['normalized_base_score']}/100 → {summary['percentage_net']}% "
        f"(scoring {summary.get('scoring_version', SCORING_DEFAULT_VERSION)})",
    )
    table.add_row(
        "Conclusion",
        f"Positive Net: {summary['raw_total_score']}/{summary['positive_points_possible']} ({summary['percentage_net']}%)",
        style="bold green",
    )
    console.print(table)


if __name__ == "__main__":
    cli()
