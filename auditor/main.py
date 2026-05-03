import click
import json
import os
import re
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader
from rich.console import Console
from rich.table import Table

from scoring_config import TECHNICAL_STATS_SCORING_CONFIG, TRACE_SCORING_CONFIG
from modules.dynamic_analysis import AuthTester, DockerOrchestrator, E2EFunctionalTester, MakefileRunner, PerformanceBenchmarker
from modules.static_analysis import AuthImplementationChecker, CodeQualityChecker, CodeSmellAnalyzer, DualPersistenceChecker, HexagonalComplianceChecker, ProjectStatsAnalyzer, ReadmeChecker, UseCaseInjectionChecker

console = Console()


def _md_cell(value: Any, max_len: int = 800) -> str:
    """Sanitize values for safe markdown table cell rendering."""
    if value is None:
        return ""
    text = str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("|", "\\|")
    text = text.replace("\n", "<br>")
    if len(text) > max_len:
        return f"{text[:max_len]}..."
    return text


def _aggregate_status(statuses: List[str]) -> str:
    if not statuses:
        return "INCONNU"
    if any(status in ("KO", "MALUS", "DETECTE") for status in statuses):
        return "KO"
    if any(status == "PARTIEL" for status in statuses):
        return "PARTIEL"
    if all(status == "SKIPPED" for status in statuses):
        return "SKIPPED"
    if any(status == "OK" for status in statuses):
        return "OK"
    return statuses[0]


def _fibonacci(index: int) -> int:
    if index <= 0:
        return 0
    if index == 1:
        return 1
    if index == 2:
        return 2
    a, b = 1, 2
    for _ in range(3, index + 1):
        a, b = b, a + b
    return b


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value: Any, decimals: int = 2) -> str:
    numeric = _to_float(value)
    if numeric is None:
        return str(value)
    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.{decimals}f}"


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _parse_test_results(output: str) -> Dict[str, int]:
    """Parses Jest-style test output for passed/failed/total counts."""
    res = {"passed": 0, "failed": 0, "total": 0}
    
    # Matches "5 passed", "1 failed", "6 total" independently to be robust
    passed_match = re.search(r"(\d+)\s+passed", output)
    if passed_match:
        res["passed"] = int(passed_match.group(1))
        
    failed_match = re.search(r"(\d+)\s+failed", output)
    if failed_match:
        res["failed"] = int(failed_match.group(1))
        
    total_match = re.search(r"(\d+)\s+total", output)
    if total_match:
        res["total"] = int(total_match.group(1))
        
    return res


def _parse_coverage_results(output: str) -> Dict[str, Any]:
    """Parses Jest --coverage output for global line/statement coverage percentage."""
    # Istanbul text table: "All files | 78.57 | ..."
    table = re.search(r'All files\s*\|\s*([\d.]+)', output)
    if table:
        return {"coverage_pct": float(table.group(1)), "source": "table"}
    # Istanbul summary: "Lines        : 78.57% ( 22/28 )"
    lines = re.search(r'Lines\s*[:\|]\s*([\d.]+)\s*%', output, re.IGNORECASE)
    if lines:
        return {"coverage_pct": float(lines.group(1)), "source": "summary_lines"}
    # Statements fallback
    stmts = re.search(r'Statements\s*[:\|]\s*([\d.]+)\s*%', output, re.IGNORECASE)
    if stmts:
        return {"coverage_pct": float(stmts.group(1)), "source": "summary_stmts"}
    return {"coverage_pct": None, "source": "not_found"}


def _build_trace_metrics(traceability: Dict[str, Any]) -> Dict[str, Any]:
    metrics = {
        "phases_count": traceability.get("phases_count", 0),
        "total_turns": None,
        "total_tool_calls": None,
        "total_wall_time_seconds": None,
    }
    data = traceability.get("data", {})
    summary = data.get("summary", {})
    phases = data.get("phases", [])

    if summary:
        metrics["total_turns"] = _to_float(summary.get("total_turns"))
        metrics["total_tool_calls"] = _to_float(summary.get("total_tool_calls"))
        metrics["total_wall_time_seconds"] = _to_float(summary.get("total_wall_time_seconds"))

    if not isinstance(phases, list) or not phases:
        return metrics

    durations: List[float] = []
    turns: List[float] = []
    tool_calls: List[float] = []

    for phase in phases:
        if not isinstance(phase, dict):
            continue

        start_dt = _parse_iso_datetime(phase.get("start_time", ""))
        end_dt = _parse_iso_datetime(phase.get("end_time", ""))
        if start_dt and end_dt:
            durations.append((end_dt - start_dt).total_seconds())

        # Support both new field names (turns_in_phase) and legacy (turns_in_step)
        p_turns = _to_float(phase.get("turns_in_phase") or phase.get("turns_in_step"))
        if p_turns is not None:
            turns.append(p_turns)

        p_tools = _to_float(phase.get("tool_calls_in_phase") or phase.get("tool_calls_in_step"))
        if p_tools is not None:
            tool_calls.append(p_tools)

    if metrics["total_turns"] is None and turns:
        metrics["total_turns"] = sum(turns)
    if metrics["total_tool_calls"] is None and tool_calls:
        metrics["total_tool_calls"] = sum(tool_calls)
    if metrics["total_wall_time_seconds"] is None and durations:
        metrics["total_wall_time_seconds"] = sum(durations)
        
    return metrics


def _score_from_bands(value: Any, bands: List[Dict[str, Any]]) -> Dict[str, Any]:
    numeric = _to_float(value)
    if numeric is None:
        return {
            "status": "SKIPPED",
            "score_ratio": 0.0,
            "remarks": "value is not numeric",
        }

    def in_band(min_value: Optional[float], max_value: Optional[float]) -> bool:
        if min_value is not None and numeric < min_value:
            return False
        if max_value is not None and numeric > max_value:
            return False
        return True

    for band in bands:
        min_value = band.get("min")
        max_value = band.get("max")
        if in_band(min_value, max_value):
            min_text = "-inf" if min_value is None else _format_number(min_value)
            max_text = "+inf" if max_value is None else _format_number(max_value)
            return {
                "status": band["status"],
                "score_ratio": band["score_ratio"],
                "remarks": f"value={_format_number(numeric)}; tranche={min_text}..{max_text}; label={band['label']}",
            }

    return {
        "status": "KO",
        "score_ratio": 0.0,
        "remarks": f"value={_format_number(numeric)}; tranche=out_of_range",
    }


def _append_scored_indicator_from_config(
    audit_db: Dict[str, Any],
    config: Dict[str, Any],
    measured_value: Any,
    trace_or_stats_present: bool = True,
) -> None:
    band_result = _score_from_bands(measured_value, config["bands"])
    
    remarks = band_result["remarks"]
    if "description" in config:
        remarks = f"{config['description']} | {remarks}"

    _append_indicator(
        audit_db,
        config["phase_number"],
        config["phase_label"],
        config["step_number"],
        config["step_label"],
        config["name"],
        band_result["score_ratio"] > 0,
        remarks,
        polarity=config.get("polarity", "positive"),
        status=band_result["status"] if trace_or_stats_present else "SKIPPED",
        details={
            "measured_value": measured_value,
            "bands": config["bands_label"],
        },
        score_ratio=band_result["score_ratio"] if trace_or_stats_present else 0.0,
        measured_value=measured_value,
        weight=config.get("weight"),
    )


def _make_status_line(result: Dict[str, Any]) -> str:
    exit_code = result.get("exit_code")
    if exit_code is not None:
        message = f"exit_code={exit_code}"
    else:
        message = result.get("status", "UNKNOWN")
    extra = _first_non_empty(result.get("error"), result.get("details"))
    return f"{message}; {extra}" if extra else message


def _phase_entry(audit_db: Dict[str, Any], phase_number: int, phase_label: str) -> Dict[str, Any]:
    for phase in audit_db["phases"]:
        if phase["number"] == phase_number:
            return phase
    phase = {
        "number": phase_number,
        "code": str(phase_number),
        "label": phase_label,
        "status": "PENDING",
        "steps": [],
        "positive_points_earned": 0,
        "positive_points_possible": 0,
        "negative_points": 0,
        "raw_total": 0,
    }
    audit_db["phases"].append(phase)
    return phase


def _step_entry(phase: Dict[str, Any], step_number: int, step_label: str) -> Dict[str, Any]:
    for step in phase["steps"]:
        if step["number"] == step_number:
            return step
    step = {
        "number": step_number,
        "code": f"{phase['number']}-{step_number}",
        "label": step_label,
        "status": "PENDING",
        "indicators": [],
        "positive_points_earned": 0,
        "positive_points_possible": 0,
        "negative_points": 0,
        "raw_total": 0,
    }
    phase["steps"].append(step)
    return step


def _append_indicator(
    audit_db: Dict[str, Any],
    phase_number: int,
    phase_label: str,
    step_number: int,
    step_label: str,
    name: str,
    achieved: bool,
    remarks: str,
    polarity: str = "positive",
    status: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    kind: str = "scored",
    measured_value: Optional[Any] = None,
    score_ratio: float = 1.0,
    rank: Optional[int] = None,
    weight: Optional[float] = None,
) -> Dict[str, Any]:
    phase = _phase_entry(audit_db, phase_number, phase_label)
    step = _step_entry(phase, step_number, step_label)
    indicator_number = len(step["indicators"]) + 1
    
    if weight is not None:
        actual_weight = weight
    else:
        fibonacci_rank = rank if rank is not None else indicator_number
        actual_weight = _fibonacci(fibonacci_rank)
    
    if kind == "measured":
        if status is None:
            status = "MESURE"
        score = None
        max_score = None
    else:
        if status is None:
            if polarity == "negative":
                status = "DETECTE" if achieved else "NON_DETECTE"
            else:
                status = "OK" if achieved else "KO"

        score = 0
        if status != "SKIPPED":
            if polarity == "negative":
                score = -round(actual_weight * score_ratio, 2) if achieved else 0
            else:
                score = round(actual_weight * score_ratio, 2) if achieved else 0
        max_score = actual_weight

    indicator = {
        "phase_number": phase_number,
        "phase_label": phase_label,
        "step_number": step_number,
        "step_label": step_label,
        "indicator_number": indicator_number,
        "code": f"{phase_number}-{step_number}-{indicator_number}",
        "name": name,
        "status": status,
        "kind": kind,
        "polarity": polarity,
        "fibonacci_rank": rank or indicator_number,
        "max_score": max_score,
        "score": score,
        "measured_value": measured_value,
        "remarks": remarks,
        "details": details or {},
    }
    step["indicators"].append(indicator)
    audit_db["indicators"].append(indicator)
    return indicator


def _finalize_audit_db(audit_db: Dict[str, Any]) -> None:
    for phase in audit_db["phases"]:
        phase_statuses: List[str] = []
        phase_positive_earned = 0
        phase_positive_possible = 0
        phase_negative_points = 0
        phase_raw_total = 0

        for step in phase["steps"]:
            step_statuses = [indicator["status"] for indicator in step["indicators"]]
            step["status"] = _aggregate_status(step_statuses)
            step["positive_points_earned"] = sum(
                indicator["score"]
                for indicator in step["indicators"]
                if indicator["kind"] == "scored" and indicator["polarity"] == "positive" and indicator["score"] > 0
            )
            step["positive_points_possible"] = sum(
                indicator["max_score"]
                for indicator in step["indicators"]
                if indicator["kind"] == "scored" and indicator["polarity"] == "positive"
            )
            step["negative_points"] = sum(
                indicator["score"]
                for indicator in step["indicators"]
                if indicator["kind"] == "scored" and indicator["score"] is not None and indicator["score"] < 0
            )
            step["raw_total"] = sum(
                indicator["score"]
                for indicator in step["indicators"]
                if indicator["kind"] == "scored" and indicator["score"] is not None
            )

            phase_statuses.append(step["status"])
            phase_positive_earned += step["positive_points_earned"]
            phase_positive_possible += step["positive_points_possible"]
            phase_negative_points += step["negative_points"]
            phase_raw_total += step["raw_total"]

        phase["status"] = _aggregate_status(phase_statuses)
        phase["positive_points_earned"] = phase_positive_earned
        phase["positive_points_possible"] = phase_positive_possible
        phase["negative_points"] = phase_negative_points
        phase["raw_total"] = phase_raw_total

    positive_points_earned = sum(
        indicator["score"]
        for indicator in audit_db["indicators"]
        if indicator["kind"] == "scored" and indicator["polarity"] == "positive" and indicator["score"] > 0
    )
    positive_points_possible = sum(
        indicator["max_score"]
        for indicator in audit_db["indicators"]
        if indicator["kind"] == "scored" and indicator["polarity"] == "positive"
    )
    negative_points = sum(
        indicator["score"]
        for indicator in audit_db["indicators"]
        if indicator["kind"] == "scored" and indicator["score"] is not None and indicator["score"] < 0
    )
    raw_total = sum(
        indicator["score"]
        for indicator in audit_db["indicators"]
        if indicator["kind"] == "scored" and indicator["score"] is not None
    )
    percentage_net = (
        round((raw_total / positive_points_possible) * 100, 2)
        if positive_points_possible
        else 0.0
    )

    audit_db["summary"] = {
        "raw_total_score": raw_total,
        "positive_points_earned": positive_points_earned,
        "positive_points_possible": positive_points_possible,
        "negative_points": negative_points,
        "percentage_net": percentage_net,
        "indicators_count": len(audit_db["indicators"]),
        "measured_indicators_count": sum(1 for indicator in audit_db["indicators"] if indicator["kind"] == "measured"),
        "scored_indicators_count": sum(1 for indicator in audit_db["indicators"] if indicator["kind"] == "scored"),
    }
    audit_db["points"] = [
        {
            "id": phase["number"],
            "label": phase["label"],
            "status": phase["status"],
            "score": phase["raw_total"],
            "max_score": phase["positive_points_possible"],
            "positive_points_earned": phase["positive_points_earned"],
            "positive_points_possible": phase["positive_points_possible"],
            "negative_points": phase["negative_points"],
        }
        for phase in audit_db["phases"]
    ]


class TraceabilityValidator:
    def __init__(self, target_path: str):
        self.target_path = target_path
        self.trace_file = os.path.join(target_path, "audit_trace.json")

    def validate(self) -> Dict[str, Any]:
        if not os.path.exists(self.trace_file):
            return {"status": "KO", "error": "audit_trace.json not found", "phases_count": 0}
        try:
            with open(self.trace_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            phases = data.get("phases", [])
            return {"status": "OK", "phases_count": len(phases), "data": data}
        except Exception as e:
            return {"status": "KO", "error": str(e), "phases_count": 0}


@click.group()
def cli() -> None:
    """AI Agent Deliverable Auditor CLI"""


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--skip-dynamic", is_flag=True, help="Skip docker and dynamic tests")
def analyze(path: str, skip_dynamic: bool) -> None:
    """Analyze a deliverable at the given PATH"""
    console.print(f"[bold blue]Starting Full Audit for:[/bold blue] {path}")
    audit_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    audit_db: Dict[str, Any] = {
        "meta": {
            "target_path": path,
            "audit_started_at": audit_started_at,
            "audit_finished_at": None,
            "skip_dynamic": skip_dynamic,
            "scoring_model": "indicator_fibonacci_v1",
        },
        "summary": {},
        "phases": [],
        "indicators": [],
        "points": [],
    }

    make = MakefileRunner(path)
    op_results: Dict[str, Dict[str, Any]] = {}

    expected_e2e_steps = [
        "List Tasks (Initial)",
        "Create Task A",
        "Get Task A",
        "Create Task B (Dependent on A)",
        "Close B (Should Fail)",
        "Close A (Success)",
        "Close B (Now Success)"
    ]

    auth_step_weights: Dict[str, int] = {
        "Auth: Accès non-authentifié bloqué": 10,
        "Auth: Inscription (register)": 5,
        "Auth: Connexion (login)": 5,
        "Auth: Opération authentifiée autorisée": 5,
        "Auth: Token falsifié rejeté": 10,
    }

    # 1. Setup
    console.print("Running make setup...")
    op_results["setup"] = make.run_target("setup")
    _append_indicator(
        audit_db, 1, "Opérationnalité", 1, "Exécution des cibles make & Docker", "make setup",
        op_results["setup"]["status"] == "OK", _make_status_line(op_results["setup"]),
        details=op_results["setup"], weight=1
    )

    # 2. Start Docker (Included in Step 1-1)
    orchestrator = DockerOrchestrator(path)
    docker_start = {"status": "SKIPPED", "details": "skipped"}
    exposed_containers = {"containers": [], "status": "SKIPPED"}
    if not skip_dynamic:
        console.print("Starting Docker infrastructure (make start)...")
        docker_start = orchestrator.start()
    
    _append_indicator(
        audit_db, 1, "Opérationnalité", 1, "Exécution des cibles make & Docker", "make start",
        docker_start["status"] == "OK", _make_status_line(docker_start),
        status=docker_start["status"] if docker_start["status"] == "SKIPPED" else None,
        details=docker_start, weight=10
    )

    # Individual Container KPIs
    if docker_start["status"] == "OK":
        exposed_containers = orchestrator.inspect_exposed_containers()
        containers_list = exposed_containers.get("containers", [])
        if not containers_list:
             _append_indicator(
                audit_db, 1, "Opérationnalité", 1, "Exécution des cibles make & Docker", "Conteneurs actifs",
                False, "Aucun conteneur détecté", details=exposed_containers, weight=2
            )
        for container in containers_list:
            _append_indicator(
                audit_db, 1, "Opérationnalité", 1, "Exécution des cibles make & Docker", f"Conteneur : {container['name']}",
                container["state"] in ("running", "up", "active"),
                f"state={container['state']}, status={container['status']}",
                details=container, weight=2
            )

    # 3. Build, Lint, Test
    console.print("Running make build...")
    op_results["build"] = make.run_target("build")
    _append_indicator(
        audit_db, 1, "Opérationnalité", 1, "Exécution des cibles make & Docker", "make build",
        op_results["build"]["status"] == "OK", _make_status_line(op_results["build"]),
        details=op_results["build"], weight=10
    )

    console.print("Running make lint...")
    op_results["lint"] = make.run_target("lint")
    _append_indicator(
        audit_db, 1, "Opérationnalité", 1, "Exécution des cibles make & Docker", "make lint",
        op_results["lint"]["status"] == "OK", _make_status_line(op_results["lint"]),
        details=op_results["lint"], weight=5
    )

    console.print("Running make test...")
    op_results["test"] = make.run_target("test")
    _append_indicator(
        audit_db, 1, "Opérationnalité", 1, "Exécution des cibles make & Docker", "make test",
        op_results["test"]["status"] == "OK", _make_status_line(op_results["test"]),
        details=op_results["test"], weight=10
    )

    is_operational = op_results["build"]["status"] == "OK"

    # Detect version obsolete in command outputs (flexible regex)
    version_obsolete_count = 0
    obsolete_pattern = re.compile(r"attribute .*version.* is obsolete", re.IGNORECASE)
    for res in list(op_results.values()) + [docker_start]:
        out = str(res.get("output", "")) + " " + str(res.get("error", "")) + " " + str(res.get("stderr", ""))
        version_obsolete_count += len(obsolete_pattern.findall(out))

    traceability = TraceabilityValidator(path).validate()
    hexagonal = HexagonalComplianceChecker(path).check()
    readme = ReadmeChecker(path).check()
    quality = CodeQualityChecker(path).check_any_usage()
    stats = ProjectStatsAnalyzer(path).analyze()
    smells = CodeSmellAnalyzer(path).analyze()
    auth_static = AuthImplementationChecker(path).check()
    dual_persistence = DualPersistenceChecker(path).check()
    injection = UseCaseInjectionChecker(path).check()
    trace_metrics = _build_trace_metrics(traceability)

    # Parse test execution results early
    test_out = ""
    if "test" in op_results:
        test_out = str(op_results["test"].get("output", "")) + str(op_results["test"].get("error", ""))
    test_results = _parse_test_results(test_out)
    coverage_data = _parse_coverage_results(test_out)
    stats["execution_test_passed"] = test_results.get("passed", 0)
    stats["execution_test_failed"] = test_results.get("failed", 0)
    stats["execution_test_total"] = test_results.get("total", 0)
    stats["coverage_pct"] = coverage_data.get("coverage_pct")

    # Add Docker Obsolete Malus as FIRST malus to ensure -1pt (rank 1)
    smells.setdefault("all_maluses", []).insert(0, {
        "id": "docker_version_obsolete",
        "reason": "Docker version attribute is obsolete",
        "status": "DETECTE" if version_obsolete_count > 0 else "NON_DETECTE",
        "count": version_obsolete_count,
        "detail": f"obsolete_detected_count={version_obsolete_count}",
    })

    performance = {"avg_latency_ms": 0, "p95_ms": 0, "error_rate": 0}
    e2e_results: List[Dict[str, Any]] = []
    auth_e2e_results: List[Dict[str, Any]] = []
    auth_token: Optional[str] = None

    # Step 1-2: Validation fonctionnelle E2E
    if docker_start["status"] == "OK":
        endpoint = "http://localhost:4000/graphql"

        console.print("Running Auth scenario...")
        auth_tester = AuthTester(endpoint)
        auth_e2e_results = auth_tester.run_scenario()
        auth_token = auth_tester.token

        e2e = E2EFunctionalTester(endpoint, token=auth_token)
        perf = PerformanceBenchmarker(endpoint, token=auth_token)

        console.print("Running E2E Scenario...")
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
                details=e2e_step, weight=5
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
                    status="SKIPPED", weight=5
                )

        console.print("Running Performance Benchmark...")
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
            details=performance, weight=5
        )
        # Auth E2E indicators (Phase 1, Step 4)
        executed_auth_steps = [r["step"] for r in auth_e2e_results]
        for auth_step in auth_e2e_results:
            _append_indicator(
                audit_db, 1, "Opérationnalité", 4, "Validation sécurité E2E",
                auth_step["step"],
                bool(auth_step.get("success")),
                _first_non_empty(auth_step.get("error"), "validated"),
                details=auth_step,
                weight=auth_step_weights.get(auth_step["step"], 5),
            )
        for step_name, w in auth_step_weights.items():
            if step_name not in executed_auth_steps:
                _append_indicator(
                    audit_db, 1, "Opérationnalité", 4, "Validation sécurité E2E",
                    step_name, False, "Step not reached",
                    status="SKIPPED", weight=w,
                )

        orchestrator.stop()
    else:
        # Fallback for failed/skipped docker start
        reason = docker_start.get("error", "runtime not started")
        if skip_dynamic:
            reason = "dynamic phase skipped"
        elif not is_operational:
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
                status="SKIPPED", weight=5
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
            details=performance, weight=5
        )
        for step_name, w in auth_step_weights.items():
            _append_indicator(
                audit_db, 1, "Opérationnalité", 4, "Validation sécurité E2E",
                step_name, False, reason, status="SKIPPED", weight=w,
            )

    # Step 1-3: Résultats détaillés des tests unitaires
    passed_count = stats.get("execution_test_passed", 0)
    failed_count = stats.get("execution_test_failed", 0)

    # Scoring logic for Passed Tests (Target 21 points)
    # 0..1=1pt (ratio 0.05), 2..5=3pts (0.14), 6..13=10pts (0.47), 14..21=21pts (1.0)
    passed_ratio = 0.0
    if passed_count >= 14: passed_ratio = 1.0
    elif passed_count >= 6: passed_ratio = 0.47
    elif passed_count >= 2: passed_ratio = 0.14
    elif passed_count >= 0: passed_ratio = 0.05

    _append_indicator(
        audit_db, 1, "Opérationnalité", 3, "Résultats des tests unitaires", "Tests PASS",
        passed_count > 0, f"count={passed_count}", score_ratio=passed_ratio, weight=21
    )

    # Scoring logic for Failed Tests (Malus up to -21 points)
    failed_ratio = 0.0
    if failed_count >= 14: failed_ratio = 1.0
    elif failed_count >= 6: failed_ratio = 0.47
    elif failed_count >= 2: failed_ratio = 0.14
    elif failed_count >= 1: failed_ratio = 0.05

    _append_indicator(
        audit_db, 1, "Opérationnalité", 3, "Résultats des tests unitaires", "Tests FAIL",
        failed_count > 0, f"count={failed_count}", polarity="negative", score_ratio=failed_ratio, weight=21
    )

    # Coverage indicator — bands: ≥80%=100%, ≥60%=50%, else=0%
    cov_pct = coverage_data.get("coverage_pct")
    cov_ratio = 0.0
    if cov_pct is not None:
        if cov_pct >= 80.0: cov_ratio = 1.0
        elif cov_pct >= 60.0: cov_ratio = 0.5
    _append_indicator(
        audit_db, 1, "Opérationnalité", 3, "Résultats des tests unitaires", "Couverture de code (%)",
        cov_pct is not None and cov_pct >= 60.0,
        f"coverage={cov_pct}% (source={coverage_data.get('source')})" if cov_pct is not None else "non détectée — --coverage manquant ?",
        score_ratio=cov_ratio, weight=15,
    )

    if hexagonal.get("rules"):
        for rule in hexagonal.get("rules", []):
            _append_indicator(
                audit_db,
                2,
                "Architecture & Qualité",
                1,
                "Conformité hexagonale",
                rule.get("rule", "Unknown rule"),
                rule.get("status") == "OK",
                f"violations_count={rule.get('violations_count', 0)}",
                details=rule, weight=15
            )
    else:
        _append_indicator(
            audit_db,
            2,
            "Architecture & Qualité",
            1,
            "Conformité hexagonale",
            "Analyse hexagonale",
            hexagonal.get("status") == "OK",
            _first_non_empty(hexagonal.get("error"), hexagonal.get("status")),
            details=hexagonal, weight=15
        )

    _append_indicator(
        audit_db,
        2,
        "Architecture & Qualité",
        2,
        "Qualité de typage",
        "Occurrences de any",
        quality.get("status") == "OK",
        f"any_count={quality.get('any_count', 0)}, ts_files={quality.get('ts_files', 0)}",
        status=quality.get("status"),
        details=quality, weight=8
    )

    _append_indicator(
        audit_db,
        2,
        "Architecture & Qualité",
        3,
        "Documentation du projet",
        "Présence du README.md",
        readme.get("found", False),
        "Fichier README.md trouvé à la racine" if readme.get("found") else "Fichier README.md manquant",
        details=readme, weight=2
    )

    if readme.get("found"):
        for key, val in readme.get("indicators", {}).items():
            _append_indicator(
                audit_db,
                2,
                "Architecture & Qualité",
                3,
                "Documentation du projet",
                f"Contenu : {key}",
                val,
                "Présent" if val else "Manquant",
                details=readme, weight=1
            )

    # Phase 2, Step 4: Auth static analysis
    for key, label, w in [
        ("jwt_library_present",      "Bibliothèque JWT (jsonwebtoken / jose)", 3),
        ("auth_mutations_present",   "Mutations register / login présentes",   5),
        ("auth_guard_present",       "Middleware / Guard d'authentification",   5),
        ("password_hashing_present", "Hachage de mot de passe (bcrypt/argon2)", 3),
    ]:
        _append_indicator(
            audit_db, 2, "Architecture & Qualité", 4, "Sécurité & Authentification",
            label,
            bool(auth_static.get("indicators", {}).get(key, False)),
            f"detected={'yes' if auth_static.get('indicators', {}).get(key) else 'no'}",
            details=auth_static, weight=w,
        )

    # Phase 2, Step 5: Use case injection (constructor DI)
    for key, label, w in [
        ("no_direct_instantiation_in_core",  "Pas d'instanciation directe dans Core",       10),
        ("injectable_decorator_used",         "@injectable() sur les use cases",              5),
        ("inject_on_constructor_params",      "@inject() sur les paramètres constructeur",    5),
        ("constructors_receive_dependencies", "Constructeurs avec dépendances injectées",     8),
    ]:
        val = bool(injection.get("indicators", {}).get(key, False))
        violations = injection.get("violations", [])
        detail = f"violations={len(violations)}" if key == "no_direct_instantiation_in_core" and violations else f"detected={'yes' if val else 'no'}"
        _append_indicator(
            audit_db, 2, "Architecture & Qualité", 5, "Injection de Dépendances (Use Cases)",
            label, val, detail, details=injection, weight=w,
        )

    # Phase 2, Step 6: Dual persistence static analysis
    for key, label, w in [
        ("mongoose_installed",      "Mongoose installé (MongoDB / tasks)",               5),
        ("sql_orm_installed",       "ORM SQL installé (TypeORM/Sequelize/mysql2)",        5),
        ("mongoose_in_task_code",   "Mongoose utilisé dans les fichiers Task",            8),
        ("sql_in_user_auth_code",   "ORM SQL utilisé dans les fichiers User/Auth",        8),
        ("separate_db_adapters",    "Adaptateurs séparés dans src/adapters/ (mongo+sql)", 5),
    ]:
        _append_indicator(
            audit_db, 2, "Architecture & Qualité", 5, "Double Persistance (MySQL+MongoDB)",
            label,
            bool(dual_persistence.get("indicators", {}).get(key, False)),
            f"detected={'yes' if dual_persistence.get('indicators', {}).get(key) else 'no'}",
            details=dual_persistence, weight=w,
        )

    trace_file_present = traceability["status"] == "OK"
    _append_indicator(
        audit_db,
        3,
        "Traçabilité",
        1,
        "Validation audit_trace.json",
        "Fichier audit_trace.json",
        trace_file_present,
        _first_non_empty(
            f"phases_count={traceability.get('phases_count', 0)}" if trace_file_present else None,
            traceability.get("error"),
            traceability.get("status"),
        ),
        details=traceability, weight=1
    )
    _append_indicator(
        audit_db,
        3,
        "Traçabilité",
        1,
        "Validation audit_trace.json",
        "Nombre de phases tracées >= 1",
        traceability.get("phases_count", 0) >= 1,
        f"phases_count={traceability.get('phases_count', 0)}",
        status="SKIPPED" if not trace_file_present else None,
        details=traceability, weight=2
    )
    for metric_key, config in TRACE_SCORING_CONFIG.items():
        _append_scored_indicator_from_config(
            audit_db,
            config,
            trace_metrics.get(metric_key),
            trace_or_stats_present=trace_file_present,
        )

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
            details=malus, weight=m_weight
        )

    for metric_key, config in TECHNICAL_STATS_SCORING_CONFIG.items():
        _append_scored_indicator_from_config(
            audit_db,
            config,
            stats.get(metric_key),
        )

    _finalize_audit_db(audit_db)
    audit_db["meta"]["audit_finished_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    audit_db["stats"] = stats

    try:
        tree_output = subprocess.run(
            ["tree", "-a", "-I", "node_modules|dist|build|tmp|.git|__pycache__|.pytest_cache|venv|.claude|coverage|tests", path],
            capture_output=True,
            text=True,
            check=False
        ).stdout
    except Exception as e:
        tree_output = f"Erreur lors de l'exécution de tree: {e}"

    audit_db["artifacts"] = {
        "make_targets": op_results,
        "docker_start": docker_start,
        "exposed_containers": exposed_containers,
        "e2e_results": e2e_results,
        "auth_e2e_results": auth_e2e_results,
        "auth_token_obtained": auth_token is not None,
        "performance": performance,
        "hexagonal": hexagonal,
        "quality": quality,
        "auth_static": auth_static,
        "dual_persistence": dual_persistence,
        "injection": injection,
        "coverage": coverage_data,
        "traceability": traceability,
        "trace_metrics": trace_metrics,
        "smells": smells,
        "project_tree": tree_output,
    }

    env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")))
    env.filters["md_cell"] = _md_cell
    template = env.get_template("report.md")

    report_content = template.render(audit_data=audit_db, stats=stats)

    output_dir = "cr_audits"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

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
    with open(os.path.join(path, "audit_report.md"), "w", encoding="utf-8") as f:
        f.write(report_content)

    summary = audit_db["summary"]
    console.print(
        f"[bold green]Audit Complete! Score Net: {summary['raw_total_score']}/"
        f"{summary['positive_points_possible']} ({summary['percentage_net']}%)[/bold green]"
    )
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
        "Conclusion",
        f"Positive Net: {summary['raw_total_score']}/{summary['positive_points_possible']} ({summary['percentage_net']}%)",
        style="bold green"
    )
    console.print(table)


if __name__ == "__main__":
    cli()
