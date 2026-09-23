"""Briques communes de normalisation (tous benchmarks) : identité d'un run déduite du nom
du livrable, métadonnées de trace, indicateurs d'une phase, corrections manuelles."""

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


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


def is_test_artifact(entry: dict[str, Any]) -> bool:
    target_path = entry.get("target_path", "")
    return target_path.startswith("/tmp/") or "pytest" in target_path


def load_overrides(path: Path) -> dict[str, Any]:
    """Load sites/<bench>/overrides.json ({} if absent/unreadable).

    Structure: {"<entry_id>": {"model": "...", "effort": "...", ...}} — tracked,
    reversible manual corrections applied on top of the raw cr_audits data. ``path``
    points another KB (each site) at its own overrides file.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        print(f"[WARN] overrides.json unreadable: {exc}", file=sys.stderr)
        return {}


def apply_overrides(
    entry: dict[str, Any],
    overrides: dict[str, Any],
    sections_builder: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> dict[str, Any]:
    """Shallow-merge the manual patch for this entry id and record which keys changed
    (``_overrides_applied``) so the front can flag manually-corrected entries.
    ``sections_builder`` rebuilds the detail cards of the entry's benchmark."""
    patch = overrides.get(entry.get("id", ""))
    if isinstance(patch, dict) and patch:
        entry.update(patch)
        entry["_overrides_applied"] = sorted(patch.keys())
        # Sections are pre-built by normalize(); rebuild so they reflect the correction
        # (adds the "Corrections manuelles" section, refreshes any overridden field).
        if "sections" in entry:
            entry["sections"] = sections_builder(entry)
    return entry
