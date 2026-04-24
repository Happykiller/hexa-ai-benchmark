import click
import json
import os
from datetime import datetime
from typing import Any, Dict
from rich.console import Console
from rich.table import Table
from jinja2 import Environment, FileSystemLoader

from modules.static_analysis import HexagonalComplianceChecker, CodeQualityChecker, ProjectStatsAnalyzer, CodeSmellAnalyzer
from modules.dynamic_analysis import DockerOrchestrator, PerformanceBenchmarker, E2EFunctionalTester, MakefileRunner

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


def _aggregate_status(statuses: list[str]) -> str:
    if not statuses:
        return "UNKNOWN"
    if any(s == "FAILED" for s in statuses):
        return "FAILED"
    if any(s == "WARNING" for s in statuses):
        return "WARNING"
    if all(s == "SKIPPED" for s in statuses):
        return "SKIPPED"
    if any(s == "SUCCESS" for s in statuses):
        return "SUCCESS"
    return statuses[0]


def _module(
    module_id: str,
    label: str,
    status: str,
    indicator: str,
    data: Dict[str, Any],
    max_data: Dict[str, Any] | None = None,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "id": module_id,
        "label": label,
        "status": status,
        "indicator": indicator,
        "data": data,
        "max_data": max_data or {},
        "details": details or {},
    }


def _step(step_id: str, label: str, modules: list[Dict[str, Any]]) -> Dict[str, Any]:
    status = _aggregate_status([m["status"] for m in modules])
    return {
        "id": step_id,
        "label": label,
        "status": status,
        "modules": modules,
    }


def _phase(phase_id: str, label: str, steps: list[Dict[str, Any]], score: float, max_score: float) -> Dict[str, Any]:
    status = _aggregate_status([s["status"] for s in steps])
    return {
        "id": phase_id,
        "label": label,
        "status": status,
        "score": round(score, 2),
        "max_score": max_score,
        "steps": steps,
    }

class TraceabilityValidator:
    def __init__(self, target_path: str):
        self.target_path = target_path
        self.trace_file = os.path.join(target_path, "audit_trace.json")

    def validate(self):
        if not os.path.exists(self.trace_file):
            return {"status": "FAILED", "error": "audit_trace.json not found", "phases_count": 0}
        try:
            with open(self.trace_file, 'r') as f:
                data = json.load(f)
            phases = data.get("phases", [])
            return {"status": "SUCCESS", "phases_count": len(phases), "data": data}
        except Exception as e:
            return {"status": "FAILED", "error": str(e), "phases_count": 0}

@click.group()
def cli():
    """AI Agent Deliverable Auditor CLI"""
    pass

@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--skip-dynamic', is_flag=True, help="Skip docker and dynamic tests")
def analyze(path, skip_dynamic):
    """Analyze a deliverable at the given PATH"""
    console.print(f"[bold blue]Starting Full Audit for:[/bold blue] {path}")
    audit_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Operational Check (Makefile execution)
    make = MakefileRunner(path)
    op_results = {}
    
    console.print("Running make setup...")
    op_results["setup"] = make.run_target("setup")
    
    console.print("Running make lint...")
    op_results["lint"] = make.run_target("lint")
    
    console.print("Running make build...")
    op_results["build"] = make.run_target("build")
    
    console.print("Running make test...")
    op_results["test"] = make.run_target("test")
    
    is_operational = op_results["build"]["status"] == "SUCCESS"
    point1_status = "SUCCESS" if all(op_results[t]["status"] == "SUCCESS" for t in ("setup", "lint", "build", "test")) else "FAILED"

    # 2. Static Analysis
    traceability = TraceabilityValidator(path).validate()
    hexagonal = HexagonalComplianceChecker(path).check()
    quality = CodeQualityChecker(path).check_any_usage()
    stats = ProjectStatsAnalyzer(path).analyze()
    smells = CodeSmellAnalyzer(path).analyze()

    # 3. Dynamic & E2E
    performance = {"avg_latency_ms": 0, "p95_ms": 0, "error_rate": 0}
    e2e_results = []
    e2e_status = "SKIPPED" if skip_dynamic else "FAILED"
    docker_start = {"status": "SKIPPED", "details": "Dynamic phase skipped"}
    exposed_containers = {"status": "SKIPPED", "containers": []}
    if not skip_dynamic and is_operational:
        orchestrator = DockerOrchestrator(path)
        console.print("Starting Docker infrastructure (make start)...")
        docker_start = orchestrator.start()
        if docker_start["status"] == "SUCCESS":
            exposed_containers = orchestrator.inspect_exposed_containers()
            endpoint = "http://localhost:4000/graphql"
            e2e = E2EFunctionalTester(endpoint)
            perf = PerformanceBenchmarker(endpoint)
            
            console.print("Running E2E Scenario...")
            e2e_results = e2e.run_scenario()
            e2e_status = "SUCCESS" if all(step["success"] for step in e2e_results) else "FAILED"
            
            console.print("Running Performance Benchmark...")
            performance = perf.run_benchmark("{ tasks { id } }", {}, iterations=50)
            
            orchestrator.stop()
        else:
            console.print("[bold red]Docker failed to start.[/bold red]")
    elif is_operational:
        e2e_status = "SKIPPED"

    # 4. Global Score Calculation (Strict Weighting)
    # Operational (50 pts)
    op_score = 0
    if op_results["setup"]["status"] == "SUCCESS": op_score += 5
    if op_results["lint"]["status"] == "SUCCESS": op_score += 5
    if op_results["build"]["status"] == "SUCCESS": op_score += 10
    if op_results["test"]["status"] == "SUCCESS": op_score += 10
    
    e2e_success_count = sum(1 for r in e2e_results if r["success"])
    if e2e_results:
        op_score += (e2e_success_count / len(e2e_results)) * 20
    
    # Architecture & Quality (40 pts)
    arch_score = (hexagonal.get("score", 0) / 100) * 25
    qual_score = (quality.get("score", 0) / 100) * 15
    
    # Traceability (10 pts)
    trace_score = 10 if traceability["status"] == "SUCCESS" else 0
    
    global_score = op_score + arch_score + qual_score + trace_score + smells["total_bonus"] + smells["total_malus"]
    global_score = max(0, min(global_score, 100))

    # Max possible varies: E2E (20pts) not evaluated when skip_dynamic
    max_possible_score = 80 if skip_dynamic else 100

    # 5. Build canonical audit payload used for report + json output
    e2e_success_count = sum(1 for r in e2e_results if r["success"])
    operational_point_status = "SUCCESS"
    if op_results["build"]["status"] != "SUCCESS":
        operational_point_status = "FAILED"
    elif not skip_dynamic and e2e_status != "SUCCESS":
        operational_point_status = "FAILED"
    elif point1_status != "SUCCESS":
        operational_point_status = "WARNING"

    architecture_point_status = "SUCCESS" if hexagonal.get("status") == "SUCCESS" else "FAILED"
    quality_point_status = quality.get("status", "SKIPPED")
    traceability_point_status = "SUCCESS" if traceability["status"] == "SUCCESS" else "FAILED"
    smell_net = smells["total_bonus"] + smells["total_malus"]
    if smell_net > 0:
        bonus_point_status = "BONUS"
    elif smell_net < 0:
        bonus_point_status = "MALUS"
    else:
        bonus_point_status = "NEUTRAL"

    phases = [
        _phase(
            "phase_1_operationnalite",
            "Opérationnalité",
            [
                _step(
                    "step_make_targets",
                    "Exécution des cibles make",
                    [
                        _module(
                            "make_setup",
                            "make setup",
                            op_results["setup"]["status"],
                            "make_target_exit_code",
                            {"exit_code": op_results["setup"].get("exit_code", -1)},
                            {"expected_exit_code": 0},
                            op_results["setup"],
                        ),
                        _module(
                            "make_lint",
                            "make lint",
                            op_results["lint"]["status"],
                            "make_target_exit_code",
                            {"exit_code": op_results["lint"].get("exit_code", -1)},
                            {"expected_exit_code": 0},
                            op_results["lint"],
                        ),
                        _module(
                            "make_build",
                            "make build",
                            op_results["build"]["status"],
                            "make_target_exit_code",
                            {"exit_code": op_results["build"].get("exit_code", -1)},
                            {"expected_exit_code": 0},
                            op_results["build"],
                        ),
                        _module(
                            "make_test",
                            "make test",
                            op_results["test"]["status"],
                            "make_target_exit_code",
                            {"exit_code": op_results["test"].get("exit_code", -1)},
                            {"expected_exit_code": 0},
                            op_results["test"],
                        ),
                    ],
                ),
                _step(
                    "step_runtime_e2e",
                    "Démarrage runtime et validation E2E",
                    [
                        _module(
                            "docker_make_start",
                            "make start",
                            docker_start["status"],
                            "runtime_startup",
                            {"waited_seconds": docker_start.get("waited_seconds", 0)},
                            {"max_startup_seconds": 120},
                            docker_start,
                        ),
                        _module(
                            "docker_exposed_containers",
                            "Conteneurs exposés",
                            exposed_containers["status"],
                            "containers_detected",
                            {"count": len(exposed_containers.get("containers", []))},
                            {"min_expected": 1},
                            exposed_containers,
                        ),
                        _module(
                            "e2e_scenario",
                            "Scénario E2E dépendances",
                            e2e_status,
                            "e2e_success_ratio",
                            {"success_count": e2e_success_count, "total_steps": len(e2e_results)},
                            {"total_steps": 5},
                            {"results": e2e_results},
                        ),
                        _module(
                            "performance_benchmark",
                            "Benchmark API",
                            "SUCCESS" if performance.get("avg_latency_ms", 0) > 0 else "SKIPPED",
                            "avg_latency_ms",
                            {
                                "avg_latency_ms": performance.get("avg_latency_ms", 0),
                                "p95_ms": performance.get("p95_ms", 0),
                                "error_rate": performance.get("error_rate", 0),
                            },
                            {"max_error_rate_pct": 5},
                            performance,
                        ),
                    ],
                ),
            ],
            op_score,
            30 if skip_dynamic else 50,
        ),
        _phase(
            "phase_2_architecture_qualite",
            "Architecture & Qualité",
            [
                _step(
                    "step_architecture",
                    "Conformité hexagonale",
                    [
                        _module(
                            "hexagonal_compliance",
                            "Isolation des couches",
                            architecture_point_status,
                            "hexagonal_score",
                            {
                                "score_pct": hexagonal.get("score", 0),
                                "violations_count": len(hexagonal.get("violations", [])),
                            },
                            {"max_score_pct": 100},
                            hexagonal,
                        )
                    ],
                ),
                _step(
                    "step_code_quality",
                    "Qualité de typage",
                    [
                        _module(
                            "any_usage_check",
                            "Usage de any",
                            quality_point_status,
                            "any_count",
                            {"any_count": quality.get("any_count", 0), "ts_files": quality.get("ts_files", 0)},
                            {"max_any_count": 0},
                            quality,
                        )
                    ],
                ),
            ],
            arch_score + qual_score,
            40,
        ),
        _phase(
            "phase_3_tracabilite",
            "Traçabilité",
            [
                _step(
                    "step_audit_trace",
                    "Validation audit_trace.json",
                    [
                        _module(
                            "traceability_file_validation",
                            "audit_trace.json",
                            traceability_point_status,
                            "phases_count",
                            {"phases_count": traceability.get("phases_count", 0)},
                            {"min_phases": 1},
                            traceability,
                        )
                    ],
                )
            ],
            trace_score,
            10,
        ),
        _phase(
            "phase_4_bonus_malus",
            "Bonus / Malus",
            [
                _step(
                    "step_initiatives",
                    "Initiatives et over-engineering",
                    [
                        _module(
                            "bonus_malus_analyzer",
                            "Analyse bonus/malus",
                            "SUCCESS",
                            "bonus_malus_net",
                            {"total_bonus": smells["total_bonus"], "total_malus": smells["total_malus"], "net": smell_net},
                            {"possible_bonus_count": len(smells.get("all_bonuses", []))},
                            smells,
                        )
                    ],
                )
            ],
            smell_net,
            0,
        ),
    ]

    audit_data: Dict[str, Any] = {
        "meta": {
            "target_path": path,
            "audit_started_at": audit_started_at,
            "audit_finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "skip_dynamic": skip_dynamic,
        },
        "summary": {
            "global_score": round(global_score, 2),
            "max_possible_score": max_possible_score,
            "admission_status": "ADMIS" if global_score >= 60 else "ECHEC",
            "score_breakdown": {
                "operational": round(op_score, 2),
                "operational_max": 30 if skip_dynamic else 50,
                "architecture": round(arch_score, 2),
                "architecture_max": 25,
                "quality": round(qual_score, 2),
                "quality_max": 15,
                "traceability": trace_score,
                "traceability_max": 10,
                "bonus_malus": smell_net,
            },
        },
        "phases": phases,
        "points": [
            {
                "id": 1,
                "label": "Operationnalite",
                "status": operational_point_status,
                "score": round(op_score, 1),
                "max_score": 50,
                "max_data": {"make_targets": 4, "e2e_steps": 5},
                "details": {
                    "make_targets": op_results,
                    "docker_start": docker_start,
                    "exposed_containers": exposed_containers,
                    "e2e_status": e2e_status,
                    "e2e_results": e2e_results,
                    "e2e_success_count": e2e_success_count,
                    "performance": performance,
                },
            },
            {
                "id": 2,
                "label": "Architecture",
                "status": architecture_point_status,
                "score": round(arch_score, 1),
                "max_score": 25,
                "max_data": {"rules": len(hexagonal.get("rules", [])), "violations": len(hexagonal.get("violations", []))},
                "details": hexagonal,
            },
            {
                "id": 3,
                "label": "Qualite Code",
                "status": quality_point_status,
                "score": round(qual_score, 1),
                "max_score": 15,
                "max_data": {"quality_points": len(quality.get("points", [])), "ts_files": quality.get("ts_files", 0)},
                "details": quality,
            },
            {
                "id": 4,
                "label": "Tracabilite",
                "status": traceability_point_status,
                "score": trace_score,
                "max_score": 10,
                "max_data": {"phases_expected_min": 1},
                "details": traceability,
            },
            {
                "id": 5,
                "label": "Bonus Malus",
                "status": bonus_point_status,
                "score": smell_net,
                "max_score": 0,
                "max_data": {"possible_bonus_count": len(smells.get("all_bonuses", []))},
                "details": smells,
            },
        ],
    }

    # 6. Report Generation
    env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates')))
    env.filters["md_cell"] = _md_cell
    template = env.get_template('report.md')
    
    report_content = template.render(
        audit_data=audit_data,
        stats=stats
    )

    # Output to cr_audits folder
    output_dir = "cr_audits"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Generate filename from path: livrables/name -> cr_name_timestamp.md
    safe_name = os.path.basename(path.rstrip('/'))
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_basename = f"cr_{safe_name}_{timestamp_str}"
    report_filename = f"{report_basename}.md"
    report_path = os.path.join(output_dir, report_filename)
    report_json_path = os.path.join(output_dir, f"{report_basename}.json")

    with open(report_path, 'w') as f:
        f.write(report_content)
    with open(report_json_path, 'w', encoding='utf-8') as f:
        json.dump(audit_data, f, indent=2, ensure_ascii=False)

    # Backward-compatible local report path for existing tooling/tests.
    with open(os.path.join(path, "audit_report.md"), 'w', encoding='utf-8') as f:
        f.write(report_content)

    console.print(f"[bold green]Audit Complete! Score: {global_score}/100[/bold green]")
    console.print(f"Detailed report saved to: [cyan]{report_path}[/cyan]")
    console.print(f"Audit data JSON saved to: [cyan]{report_json_path}[/cyan]")
    
    # Summary Table
    table = Table(title=f"Audit Results - {path}")
    table.add_column("Category", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Score/Value", style="green")

    table.add_row("Operational (Build/Lint/Test)", op_results["build"]["status"], f"{op_score}/50")
    table.add_row("E2E Functional", e2e_status, f"{e2e_success_count}/{len(e2e_results)} steps")
    table.add_row("Architecture", hexagonal.get("status", "UNKNOWN"), f"{round(arch_score, 1)}/25")
    table.add_row("Code Quality", quality.get("status", "UNKNOWN"), f"{round(qual_score, 1)}/15")
    table.add_row("Bonus/Malus", f"B:{smells['total_bonus']} M:{smells['total_malus']}", f"Net: {smells['total_bonus'] + smells['total_malus']}")
    
    console.print(table)

if __name__ == "__main__":
    cli()
