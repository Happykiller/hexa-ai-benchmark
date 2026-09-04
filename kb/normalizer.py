import json
import re
import sys
from pathlib import Path
from typing import Any

from .constants import ADMISSION_THRESHOLD, OVERRIDES_PATH, SCAN_DIRS, repo_relative
from .markdown_parser import extract_report_markdown, md_files_by_stem
from .render import build_sections

DOCKER_NOISE_RE = re.compile(
    r"^\s*[a-f0-9]+\s+(Downloading|Extracting|Pull complete|Pushed|Waiting|"
    r"Pulling fs layer|Download complete|Already exists|Layer already exists)\b",
    re.IGNORECASE,
)

# MongoDB/MySQL structured JSON log lines — not useful for crash diagnosis
DB_JSON_LOG_RE = re.compile(
    r"^\s*(?:[a-zA-Z0-9_-]*(?:mongo|mysql|postgres|redis|mariadb)[a-zA-Z0-9_-]*)\s+\|\s*\{",
    re.IGNORECASE,
)

# Container service prefix: "api-1  | " or "todo_api-1  | "
CONTAINER_PREFIX_RE = re.compile(r"^\s*([a-zA-Z0-9_.-]+)\s+\|\s?", re.IGNORECASE)
API_SERVICE_RE = re.compile(r"\bapi\b", re.IGNORECASE)


def clean_output(text: str, max_lines: int = 20) -> str:
    lines = [
        line
        for line in (text or "").split("\n")
        if line.strip() and not DOCKER_NOISE_RE.match(line)
    ]
    return "\n".join(lines[-max_lines:]).strip()


def clean_container_logs(text: str, max_lines: int = 40) -> str:
    """Extract the most useful lines from container logs.

    Prioritises api-service lines (crash happens at startup, so we take
    the first lines, not the last). Falls back to generic filtering when
    no api service is found, removing structured DB JSON logs that bury
    the real error.
    """
    all_lines = [line for line in (text or "").split("\n") if line.strip()]

    # Try to isolate api-service lines (where the Node crash lives)
    api_lines = []
    for line in all_lines:
        m = CONTAINER_PREFIX_RE.match(line)
        if m and API_SERVICE_RE.search(m.group(1)):
            api_lines.append(line)

    if api_lines:
        return "\n".join(api_lines[:max_lines]).strip()

    # Fallback: strip DB JSON logs and docker layer noise, keep last N
    filtered = [
        line
        for line in all_lines
        if not DOCKER_NOISE_RE.match(line) and not DB_JSON_LOG_RE.match(line)
    ]
    return "\n".join(filtered[-max_lines:]).strip()


def agent_from_path(target_path: str) -> str:
    basename = Path(target_path.rstrip("/")).name
    match = re.match(r"^\d{8}_\d{4}_(.+)$", basename)
    return match.group(1) if match else basename


def session_from_path(target_path: str) -> str | None:
    basename = Path(target_path.rstrip("/")).name
    match = re.match(r"^(\d{8}_\d{4})_", basename)
    return match.group(1) if match else None


def trace_meta_from_artifacts(artifacts: dict[str, Any]) -> dict[str, Any]:
    traceability = artifacts.get("traceability", {})
    data = traceability.get("data", {}) if isinstance(traceability, dict) else {}
    meta = data.get("meta", {}) if isinstance(data, dict) else {}
    return meta if isinstance(meta, dict) else {}


def extract_phase_indicators(data: dict[str, Any], phase_code: str) -> list[dict[str, Any]]:
    indicators: list[dict[str, Any]] = []
    for phase in data.get("phases", []):
        if str(phase.get("code")) != phase_code:
            continue
        for step in phase.get("steps", []):
            for indicator in step.get("indicators", []):
                details = indicator.get("details") or {}
                safe_details = {key: value for key, value in details.items() if key != "data"}
                indicators.append(
                    {
                        "code": indicator.get("code"),
                        "name": indicator.get("name"),
                        "status": indicator.get("status"),
                        "score": indicator.get("score"),
                        "max_score": indicator.get("max_score"),
                        "measured_value": indicator.get("measured_value"),
                        "remarks": indicator.get("remarks"),
                        "step": step.get("label"),
                        "details": safe_details,
                    }
                )
    return indicators


def normalize_old(
    data: dict[str, Any], source_file: str, report_markdown: dict[str, Any] | None
) -> dict[str, Any]:
    meta = data.get("meta", {})
    summary = data.get("summary", {})
    target = meta.get("target_path", "")
    score_breakdown = summary.get("score_breakdown", {})

    bucket_scores = {
        "operationality": {
            "normalized_score": score_breakdown.get("operational", 0),
            "weight": score_breakdown.get("operational_max", 50),
        },
        "architecture": {
            "normalized_score": score_breakdown.get("architecture", 0),
            "weight": score_breakdown.get("architecture_max", 25),
        },
        "quality": {
            "normalized_score": score_breakdown.get("quality", 0),
            "weight": score_breakdown.get("quality_max", 15),
        },
        "traceability": {
            "normalized_score": score_breakdown.get("traceability", 0),
            "weight": score_breakdown.get("traceability_max", 10),
        },
    }
    if not score_breakdown:
        labels_map = {
            "operationnalite": "operationality",
            "architecture": "architecture",
            "qualite": "quality",
            "tracabilite": "traceability",
        }
        for point in data.get("points", []):
            key = next(
                (
                    value
                    for label, value in labels_map.items()
                    if label in point.get("label", "").lower()
                ),
                None,
            )
            if key:
                bucket_scores[key] = {
                    "normalized_score": point.get("score", 0),
                    "weight": point.get("max_score", 0),
                }

    score_pct = float(summary.get("global_score", 0))
    agent = agent_from_path(target)
    return {
        "id": Path(source_file).stem,
        "source_file": repo_relative(source_file),
        "agent": agent,
        "model": str(meta.get("model") or agent),
        "effort": str(meta.get("effort") or ""),
        "prompt_version": str(meta.get("prompt_version") or ""),
        "session_id": session_from_path(target),
        "audit_started_at": meta.get("audit_started_at", ""),
        "audit_finished_at": meta.get("audit_finished_at", ""),
        "scoring_model": "legacy",
        "score_percentage": score_pct,
        "admission_status": summary.get(
            "admission_status", "ADMIS" if score_pct >= ADMISSION_THRESHOLD else "ECHEC"
        ),
        "score_capped": False,
        "score_caps": [],
        "skip_dynamic": meta.get("skip_dynamic", False),
        "bucket_scores": bucket_scores,
        "cost": None,
        "target_path": target,
        "stats": None,
        "make_targets": None,
        "docker": None,
        "hexagonal": None,
        "auth_static": None,
        "injection": None,
        "dual_persistence": None,
        "trace_metrics": None,
        "traceability_indicators": [],
        "duration_seconds": None,
        "bonuses": None,
        "maluses": None,
        "e2e_steps": None,
        "auth_e2e_steps": None,
        "performance": None,
        "report_markdown": report_markdown,
    }


def extract_tooltips(artifacts: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    tooltips: dict[str, Any] = {}

    make: dict[str, str] = {}
    for target, result in artifacts.get("make_targets", {}).items():
        if result.get("status") != "OK":
            parts = []
            exit_code = result.get("exit_code")
            if exit_code is not None:
                parts.append(f"exit_code={exit_code}")
            error = clean_output(str(result.get("error") or result.get("output") or ""))
            if error:
                parts.append(error)
            if parts:
                make[target] = "\n".join(parts)
    docker_start = artifacts.get("docker_start", {})
    if docker_start.get("status") not in ("OK", "SKIPPED", None):
        parts = []
        err_msg = str(docker_start.get("error") or "").strip()
        if err_msg:
            parts.append(err_msg)
        compose_out = clean_output(
            str(docker_start.get("stderr") or docker_start.get("output") or "")
        )
        if compose_out:
            parts.append(compose_out)
        container_logs = clean_container_logs(str(docker_start.get("container_logs") or ""))
        if container_logs:
            parts.append("--- container logs ---\n" + container_logs)
        if parts:
            make["docker"] = "\n".join(parts)
    tooltips["make"] = make

    e2e_errors: dict[str, str] = {}
    for result in artifacts.get("e2e_results", []) + artifacts.get("auth_e2e_results", []):
        if not result.get("success") and result.get("error"):
            e2e_errors[result["step"]] = str(result["error"])
    tooltips["e2e"] = e2e_errors

    hexa_violations = artifacts.get("hexagonal", {}).get("violations", [])
    if hexa_violations:
        lines = [
            f"{violation.get('file', '')} — {violation.get('reason', '')} (import: {violation.get('pattern', '')})"
            for violation in hexa_violations[:10]
        ]
        if len(hexa_violations) > 10:
            lines.append(f"… +{len(hexa_violations) - 10} autres")
        tooltips["hexa_violations"] = "\n".join(lines)

    injection_violations = artifacts.get("injection", {}).get("violations", [])
    if injection_violations:
        tooltips["inj_violations"] = "\n".join(
            [
                f"{violation.get('file', '')} : {violation.get('pattern', '')}"
                for violation in injection_violations[:5]
            ]
        )

    traceability = artifacts.get("traceability", {})
    if traceability.get("errors"):
        tooltips["trace_errors"] = "\n".join(traceability["errors"])

    summary = data.get("summary", {})
    score_caps = summary.get("score_caps", [])
    if score_caps:
        tooltips["score_caps"] = "\n".join(cap.get("reason", "") for cap in score_caps)

    performance = artifacts.get("performance", {})
    if performance and performance.get("avg_latency_ms"):
        tooltips["perf"] = (
            f"avg={round(performance.get('avg_latency_ms', 0), 1)}ms  "
            f"p95={round(performance.get('p95_ms', 0), 1)}ms  "
            f"err_rate={round(performance.get('error_rate', 0), 1)}%"
        )

    return tooltips


def normalize_new(
    data: dict[str, Any], source_file: str, report_markdown: dict[str, Any] | None
) -> dict[str, Any]:
    meta = data.get("meta", {})
    summary = data.get("summary", {})
    artifacts = data.get("artifacts", {})
    stats = data.get("stats", {})
    target = meta.get("target_path", "")

    score_pct = float(summary.get("percentage_net", 0))
    bucket_scores = {
        key: {
            "normalized_score": value.get("normalized_score", 0),
            "weight": value.get("weight", 0),
        }
        for key, value in summary.get("bucket_scores", {}).items()
    }

    docker_start = artifacts.get("docker_start", {})
    trace_metrics = artifacts.get("trace_metrics", {})
    trace_meta = trace_meta_from_artifacts(artifacts)
    hexagonal = artifacts.get("hexagonal", {})
    smells = artifacts.get("smells", {})
    agent = agent_from_path(target)

    return {
        "id": Path(source_file).stem,
        "source_file": repo_relative(source_file),
        "agent": agent,
        "model": str(trace_meta.get("model") or agent),
        "effort": str(trace_meta.get("effort") or ""),
        "prompt_version": str(trace_meta.get("prompt_version") or ""),
        "session_id": session_from_path(target),
        "audit_started_at": meta.get("audit_started_at", ""),
        "audit_finished_at": meta.get("audit_finished_at", ""),
        "scoring_model": meta.get("scoring_model", "indicator_fibonacci_v1"),
        "score_percentage": score_pct,
        "admission_status": "ADMIS" if score_pct >= ADMISSION_THRESHOLD else "ECHEC",
        "score_capped": bool(summary.get("score_capped")),
        "score_caps": [cap.get("reason", "") for cap in summary.get("score_caps", [])],
        "skip_dynamic": meta.get("skip_dynamic", False),
        "bucket_scores": bucket_scores,
        "cost": {
            "usd": (meta.get("cost") or {}).get("cost_usd"),
            "tokens": (meta.get("cost") or {}).get("total_tokens"),
            "model_key": (meta.get("cost") or {}).get("model_key"),
            "priced": (meta.get("cost") or {}).get("priced"),
            "efficiency": summary.get("cost_efficiency_pct_per_usd"),
        },
        "target_path": target,
        "stats": {
            "files": stats.get("total_files"),
            "ts_files": stats.get("total_ts_files"),
            "lines": stats.get("total_lines"),
            "test_files": stats.get("total_tests"),
            "tests_pass": stats.get("execution_test_passed"),
            "tests_fail": stats.get("execution_test_failed"),
            "coverage": stats.get("coverage_pct"),
        },
        "make_targets": {
            key: value.get("status") for key, value in artifacts.get("make_targets", {}).items()
        },
        "docker": {
            "status": docker_start.get("status"),
            "waited_s": docker_start.get("waited_seconds"),
        },
        "hexagonal": {
            "status": hexagonal.get("status"),
            "violations": len(hexagonal.get("violations", [])),
            "rules_ok": sum(1 for rule in hexagonal.get("rules", []) if rule.get("status") == "OK"),
            "rules_total": len(hexagonal.get("rules", [])),
        },
        "auth_static": {
            key: bool(artifacts.get("auth_static", {}).get("indicators", {}).get(value))
            for key, value in [
                ("jwt", "jwt_library_present"),
                ("mutations", "auth_mutations_present"),
                ("guard", "auth_guard_present"),
                ("hashing", "password_hashing_present"),
            ]
        },
        "injection": {
            key: bool(artifacts.get("injection", {}).get("indicators", {}).get(value))
            for key, value in [
                ("no_direct", "no_direct_instantiation_in_core"),
                ("injectable", "injectable_decorator_used"),
                ("inject", "inject_on_constructor_params"),
                ("ctor_deps", "constructors_receive_dependencies"),
            ]
        },
        "dual_persistence": {
            key: bool(artifacts.get("dual_persistence", {}).get("indicators", {}).get(value))
            for key, value in [
                ("mongoose", "mongoose_installed"),
                ("sql_orm", "sql_orm_installed"),
                ("mongoose_tasks", "mongoose_in_task_code"),
                ("sql_users", "sql_in_user_auth_code"),
                ("adapters", "separate_db_adapters"),
            ]
        },
        "trace_metrics": {
            "phases": trace_metrics.get("phases_count"),
            "turns": trace_metrics.get("total_turns"),
            "tools": trace_metrics.get("total_tool_calls"),
            "wall_s": trace_metrics.get("total_wall_time_seconds"),
            "errors": trace_metrics.get("trace_errors_count", 0),
        },
        "traceability_indicators": extract_phase_indicators(data, "3"),
        "duration_seconds": trace_metrics.get("total_wall_time_seconds"),
        "bonuses": [
            {"reason": bonus.get("reason", ""), "ok": bonus.get("status") == "OK"}
            for bonus in smells.get("all_bonuses", [])
        ],
        "maluses": [
            {"reason": malus.get("reason", ""), "detected": malus.get("status") == "DETECTE"}
            for malus in smells.get("all_maluses", [])
        ],
        "e2e_steps": {
            result["step"]: bool(result.get("success"))
            for result in artifacts.get("e2e_results", [])
        },
        "auth_e2e_steps": {
            result["step"]: bool(result.get("success"))
            for result in artifacts.get("auth_e2e_results", [])
        },
        "performance": artifacts.get("performance"),
        "report_markdown": report_markdown,
        "_tooltips": extract_tooltips(artifacts, data),
    }


def normalize(
    data: dict[str, Any], source_file: str, report_markdown: dict[str, Any] | None
) -> dict[str, Any]:
    entry = (
        normalize_new(data, source_file, report_markdown)
        if data.get("meta", {}).get("scoring_model")
        else normalize_old(data, source_file, report_markdown)
    )
    entry["sections"] = build_sections(entry)
    return entry


def is_test_artifact(entry: dict[str, Any]) -> bool:
    target_path = entry.get("target_path", "")
    return target_path.startswith("/tmp/") or "pytest" in target_path


def load_overrides() -> dict[str, Any]:
    """Load knowledge_base/overrides.json ({} if absent/unreadable).

    Structure: {"<entry_id>": {"model": "...", "effort": "...", ...}} — tracked,
    reversible manual corrections applied on top of the raw cr_audits data.
    """
    if not OVERRIDES_PATH.exists():
        return {}
    try:
        data = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        print(f"[WARN] overrides.json unreadable: {exc}", file=sys.stderr)
        return {}


def apply_overrides(entry: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge the manual patch for this entry id and record which keys changed
    (``_overrides_applied``) so the front can flag manually-corrected entries."""
    patch = overrides.get(entry.get("id", ""))
    if isinstance(patch, dict) and patch:
        entry.update(patch)
        entry["_overrides_applied"] = sorted(patch.keys())
        # Sections are pre-built by normalize(); rebuild so they reflect the correction
        # (adds the "Corrections manuelles" section, refreshes any overridden field).
        if "sections" in entry:
            entry["sections"] = build_sections(entry)
    return entry


def load_all(overrides: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if overrides is None:
        overrides = load_overrides()
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    md_files = md_files_by_stem()
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in sorted(scan_dir.glob("*.json")):
            if path.stem in seen:
                continue
            seen.add(path.stem)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                report_markdown = extract_report_markdown(md_files.get(path.stem))
                entry = normalize(data, str(path), report_markdown)
                entry = apply_overrides(entry, overrides)
                if not is_test_artifact(entry):
                    entries.append(entry)
            except Exception as exc:
                print(f"[WARN] skipping {path.name}: {exc}", file=sys.stderr)
    entries.sort(key=lambda entry: entry.get("audit_started_at", ""), reverse=True)
    return entries
