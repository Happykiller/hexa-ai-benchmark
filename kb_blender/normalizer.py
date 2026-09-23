"""cr_audits_blender/cr_*.json → entrée de knowledge_base_blender/data.json."""

import json
import re
import sys
from pathlib import Path
from typing import Any

from kb.constants import ADMISSION_THRESHOLD, repo_relative
from kb.markdown_parser import extract_report_markdown, md_files_by_stem
from kb.normalizer import (
    agent_from_path,
    apply_overrides,
    extract_phase_indicators,
    is_test_artifact,
    load_overrides,
    session_from_path,
    trace_meta_from_artifacts,
)

from .constants import BUCKET_SHORT, OVERRIDES_PATH, SCAN_DIRS
from .render import build_sections


def _phases_detail(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Indicateurs par phase, allégés (sans `details`) pour les cartes de la KB."""
    keep = (
        "code",
        "name",
        "status",
        "kind",
        "polarity",
        "score",
        "max_score",
        "measured_value",
        "remarks",
    )
    return [
        {
            "number": phase["number"],
            "label": phase["label"],
            "indicators": [
                {key: indicator.get(key) for key in keep}
                for step in phase.get("steps", [])
                for indicator in step.get("indicators", [])
            ],
        }
        for phase in data.get("phases", [])
    ]


def normalize_blender(
    data: dict[str, Any], source_file: str, report_markdown: dict[str, Any] | None
) -> dict[str, Any]:
    meta = data.get("meta", {})
    summary = data.get("summary", {})
    artifacts = data.get("artifacts", {})
    target = meta.get("target_path", "")
    trace_meta = trace_meta_from_artifacts(artifacts)
    trace_metrics = artifacts.get("trace_metrics") or {}
    agent = agent_from_path(target)
    entry_id = Path(source_file).stem
    score = float(summary.get("percentage_net", 0))
    entry = {
        "id": entry_id,
        "benchmark": "blender",
        "source_file": repo_relative(source_file),
        "challenge": meta.get("challenge"),
        "challenge_label": meta.get("challenge_label"),
        "agent": agent,
        "model": re.sub(r"\[[^\]]*\]$", "", str(trace_meta.get("model") or agent)).strip(),
        "effort": str(trace_meta.get("effort") or ""),
        "prompt_version": str(trace_meta.get("prompt_version") or ""),
        "session_id": session_from_path(target),
        "target_path": target,
        "audit_started_at": meta.get("audit_started_at", ""),
        "audit_finished_at": meta.get("audit_finished_at", ""),
        "scoring_model": meta.get("scoring_model"),
        "score_percentage": score,
        "admission_status": "ADMIS" if score >= ADMISSION_THRESHOLD else "ECHEC",
        "score_capped": bool(summary.get("score_capped")),
        "score_caps": [cap.get("reason", "") for cap in summary.get("score_caps", [])],
        "skip_render": bool(meta.get("skip_render")),
        "blender_version": meta.get("blender_version"),
        "bucket_scores": {
            key: {
                "normalized_score": value.get("normalized_score", 0),
                "weight": value.get("weight", 0),
                "label": value.get("label", key),
                "short": BUCKET_SHORT.get(key, key),
            }
            for key, value in summary.get("bucket_scores", {}).items()
        },
        "cost": {
            "usd": (meta.get("cost") or {}).get("cost_usd"),
            "tokens": (meta.get("cost") or {}).get("total_tokens"),
            "model_key": (meta.get("cost") or {}).get("model_key"),
            "priced": (meta.get("cost") or {}).get("priced"),
            "efficiency": summary.get("cost_efficiency_pct_per_usd"),
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
        "blender": data.get("stats") or {},
        "phases_detail": _phases_detail(data),
        "media": [
            {
                "kind": item["kind"],
                "src": f"media/{entry_id}/{item['file']}",
                "label": item["label"],
                "file": item["file"],
            }
            for item in artifacts.get("media") or []
        ],
        "report_markdown": report_markdown,
    }
    entry["sections"] = build_sections(entry)
    return entry


def load_one(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    report = extract_report_markdown(md_files_by_stem(SCAN_DIRS).get(path.stem))
    return apply_overrides(
        normalize_blender(data, str(path), report), load_overrides(OVERRIDES_PATH), build_sections
    )


def load_all() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in sorted(scan_dir.glob("cr_*.json")):
            try:
                entry = load_one(path)
            except Exception as exc:  # noqa: BLE001 — un rapport illisible ne bloque pas les autres
                print(f"[WARN] skipping {path.name}: {exc}", file=sys.stderr)
                continue
            if not is_test_artifact(entry):
                entries.append(entry)
    entries.sort(key=lambda entry: entry.get("audit_started_at", ""), reverse=True)
    return entries
