import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import FINDING_TOKENS, SCAN_DIRS


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def parse_table_row(line: str) -> List[str]:
    if not line.startswith("|"):
        return []
    return [part.strip() for part in line.strip().strip("|").split("|")]


def safe_float(value: str) -> Optional[float]:
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", "."))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def is_benign_negative_indicator(indicator: str, score: Optional[float], remarks: str) -> bool:
    indicator_lc = (indicator or "").lower()
    remarks_lc = (remarks or "").lower()
    if score != 0:
        return False
    if "tests fail" in indicator_lc and re.search(r"\bcount\s*=\s*0\b", remarks_lc):
        return True
    if "nombre de phases tracées" in indicator_lc:
        match = re.search(r"\bphases_count\s*=\s*(\d+)\b", remarks_lc)
        if match and int(match.group(1)) >= 1:
            return True
    return False


def is_interesting_finding(indicator: str, score: Optional[float], max_score: Optional[float], remarks: str) -> bool:
    if is_benign_negative_indicator(indicator, score, remarks):
        return False
    remarks_lc = (remarks or "").lower()
    if score is not None and max_score is not None and score < max_score:
        return True
    return any(token in remarks_lc for token in FINDING_TOKENS)


def md_files_by_stem() -> Dict[str, Path]:
    files: Dict[str, Path] = {}
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in sorted(scan_dir.glob("*.md")):
            files.setdefault(path.stem, path)
    return files


def extract_report_markdown(md_path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if not md_path or not md_path.exists():
        return None

    text = md_path.read_text(encoding="utf-8")
    current_h2 = ""
    current_h3 = ""
    current_h4 = ""
    summary_metrics: Dict[str, str] = {}
    findings: List[Dict[str, Any]] = []
    trace_file_invalid = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            current_h2 = line[3:].strip()
            current_h3 = ""
            current_h4 = ""
            continue
        if line.startswith("### "):
            current_h3 = line[4:].strip()
            current_h4 = ""
            continue
        if line.startswith("#### "):
            current_h4 = line[5:].strip()
            continue
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue

        cells = parse_table_row(line)
        if not cells or cells[0] in {"Mesure", "Code", "Cible", "Etape", "Phase", "Pilier", "Règle", "Type"}:
            continue

        if current_h2 == "Résumé global" and not current_h3 and len(cells) == 2:
            summary_metrics[cells[0]] = cells[1]
            continue

        if current_h2 != "Revue détaillée des indicateurs par phase" or len(cells) < 6:
            continue

        code, indicator, _, score_raw, max_raw, remarks = cells[:6]
        score = safe_float(score_raw)
        max_score = safe_float(max_raw)
        if (
            code == "3-1-1"
            and "audit_trace" in indicator.lower()
            and score is not None
            and max_score is not None
            and score < max_score
        ):
            trace_file_invalid = True
        if trace_file_invalid and code.startswith("3-") and code != "3-1-1":
            continue
        if not is_interesting_finding(indicator, score, max_score, remarks):
            continue

        kind = "failed"
        if score is not None and max_score is not None and score > 0:
            kind = "partial"
        tooltip = "\n".join(
            part
            for part in [
                current_h3,
                current_h4,
                f"{indicator} ({score_raw}/{max_raw})" if score_raw or max_raw else indicator,
                remarks,
            ]
            if part
        )
        findings.append(
            {
                "phase": current_h3,
                "step": current_h4,
                "code": code,
                "indicator": indicator,
                "score": score,
                "max_score": max_score,
                "remarks": remarks,
                "status": score_raw,
                "kind": kind,
                "tooltip": tooltip,
            }
        )

    findings.sort(
        key=lambda item: (
            0 if item["kind"] == "failed" else 1,
            item.get("score", 0) / item.get("max_score", 1) if item.get("max_score") else 0,
            item.get("code", ""),
        )
    )
    return {
        "source_file": str(md_path),
        "summary_metrics": summary_metrics,
        "findings_count": len(findings),
        "top_findings": findings[:8],
    }
