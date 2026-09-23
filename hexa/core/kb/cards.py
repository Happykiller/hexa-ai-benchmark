"""Cartes de détail communes aux knowledge bases : éléments, sections, et les cartes qui
ne dépendent pas du benchmark (traçabilité, coût, corrections manuelles, synthèse du rapport)."""

import json
from typing import Any

from hexa.core.kb.markdown_parser import truncate


def item(
    label: str, value: str, cls: str | None = None, tooltip: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"label": label, "value": value, "cls": cls}
    if tooltip:
        payload["tooltip"] = tooltip
    return payload


def bool_item(label: str, val: bool | None, tooltip: str | None = None) -> dict[str, Any]:
    if val is None:
        return item(label, "—", "na", tooltip)
    return item(label, "✓", "ok", tooltip) if val else item(label, "✗", "ko", tooltip)


def status_item(label: str, status: str | None, tooltip: str | None = None) -> dict[str, Any]:
    cls = {"OK": "ok", "KO": "ko", "SKIPPED": "skip", "SUCCESS": "ok", "FAILED": "ko"}.get(
        status or "", "na"
    )
    return item(label, status or "?", cls, tooltip)


def section(title: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"title": title, "items": items}


def first_trace_finding(entry: dict[str, Any]) -> dict[str, Any] | None:
    report = entry.get("report_markdown") or {}
    for finding in report.get("top_findings") or []:
        code = str(finding.get("code") or "")
        phase = str(finding.get("phase") or "").lower()
        if code.startswith("3-") or "traçabilité" in phase or "traceability" in phase:
            return finding
    return None


def fmt_score(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "0"
    return str(int(numeric)) if numeric.is_integer() else f"{numeric:.1f}"


def trace_indicator_tooltip(indicator: dict[str, Any]) -> str:
    lines = [
        str(indicator.get("step") or ""),
        f"Code: {indicator.get('code') or ''}",
        f"Statut: {indicator.get('status') or '?'}",
        f"Score: {fmt_score(indicator.get('score'))}/{fmt_score(indicator.get('max_score'))}",
    ]
    if indicator.get("measured_value") is not None:
        lines.append(f"Valeur mesurée: {indicator.get('measured_value')}")
    if indicator.get("remarks"):
        lines.append(f"Remarques: {indicator.get('remarks')}")

    details = indicator.get("details") or {}
    if details:
        detail_lines = []
        for key, value in details.items():
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            if isinstance(value, dict):
                value = json.dumps(value, ensure_ascii=False)
            detail_lines.append(f"{key}: {value}")
        if detail_lines:
            lines.append("Détails:")
            lines.extend(detail_lines)

    return "\n".join(line for line in lines if line)


def trace_indicator_label(indicator: dict[str, Any]) -> str:
    code = str(indicator.get("code") or "")
    name = str(indicator.get("name") or "")
    if code == "3-1-1" and name == "Fichier audit_trace.json":
        name = "Validation audit_trace.json"
    return f"{code} {name}".strip()


def section_trace_diagnostic(entry: dict[str, Any]) -> dict[str, Any] | None:
    bucket = (entry.get("bucket_scores") or {}).get("traceability", {})
    trace_metrics = entry.get("trace_metrics") or {}
    trace_indicators = entry.get("traceability_indicators") or []
    has_bucket = bool(bucket)
    has_metrics = any(value is not None for value in trace_metrics.values())
    if not has_bucket and not has_metrics and not trace_indicators:
        return None

    norm = float(bucket.get("normalized_score", 0) or 0)
    weight = float(bucket.get("weight", 0) or 0)
    pct = round(norm / weight * 100) if weight else 0
    cls = "ok" if pct >= 70 else "warn" if pct >= 40 else "ko"

    items = [
        item("Score trace", f"{norm:.1f} / {weight:.1f} ({pct}%)" if weight else f"{norm:.1f}", cls)
    ]

    for indicator in trace_indicators:
        status = str(indicator.get("status") or "?")
        status_cls = {
            "OK": "ok",
            "KO": "ko",
            "SKIPPED": "skip",
            "FAILED": "ko",
            "PARTIEL": "warn",
        }.get(status, "na")
        score = f"{fmt_score(indicator.get('score'))}/{fmt_score(indicator.get('max_score'))}"
        label = trace_indicator_label(indicator)
        items.append(
            item(
                truncate(label, 52),
                f"{status} · {score}",
                status_cls,
                trace_indicator_tooltip(indicator),
            )
        )

    if not trace_indicators:
        trace_error = (entry.get("_tooltips") or {}).get("trace_errors")
        trace_finding = first_trace_finding(entry)
        if trace_error:
            first_error = trace_error.splitlines()[0]
            items.append(item("Trace", truncate(first_error, 72), "ko", trace_error))
        elif trace_finding:
            remarks = trace_finding.get("remarks") or trace_finding.get("status") or "à vérifier"
            items.append(
                item(
                    "Trace",
                    truncate(str(remarks), 72),
                    "ko" if trace_finding.get("kind") == "failed" else "warn",
                    trace_finding.get("tooltip"),
                )
            )

    return section("Détail traçabilité", items)


def section_report(entry: dict[str, Any]) -> dict[str, Any] | None:
    report = entry.get("report_markdown") or {}
    findings = report.get("top_findings") or []
    summary = report.get("summary_metrics") or {}
    if not report and not findings:
        return None

    items = []
    if report.get("source_file"):
        report_name = report["source_file"].split("/")[-1]
        items.append(item("Rapport MD", "rapport", tooltip=report_name))
    final_score = summary.get("Pourcentage final du score net")
    if final_score:
        items.append(item("Score rapport", final_score))
    for idx, finding in enumerate(findings[:4], start=1):
        title = finding.get("indicator") or finding.get("code") or f"Constat {idx}"
        items.append(
            item(
                f"Constat {idx}",
                truncate(
                    f"{title} — {finding.get('remarks') or finding.get('status') or 'à vérifier'}",
                    92,
                ),
                "ko" if finding.get("kind") == "failed" else "warn",
                finding.get("tooltip"),
            )
        )
    return section("Synthèse rapport", items) if items else None


def section_cost(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Estimated session cost surfaced from the auditor's meta.cost (v2 only)."""
    cost = entry.get("cost") or {}
    usd = cost.get("usd")
    tokens = cost.get("tokens")
    efficiency = cost.get("efficiency")
    if usd is None and tokens is None:
        return None
    items = []
    if usd is not None:
        items.append(item("Coût estimé", f"${usd:.4f}"))
    if tokens is not None:
        items.append(item("Tokens (in+out)", f"{int(tokens):,}".replace(",", " ")))
    if efficiency is not None:
        items.append(item("Valeur (pts/$)", f"{efficiency:.1f}"))
    if cost.get("model_key"):
        items.append(
            item("Modèle tarifé", str(cost["model_key"]), None if cost.get("priced") else "na")
        )
    return section("Coût estimé", items) if items else None


def section_overrides(entry: dict[str, Any]) -> dict[str, Any] | None:
    """Surface tracked manual corrections (from overrides.json) so they're visible."""
    applied = entry.get("_overrides_applied")
    if not applied:
        return None
    items = [item(field, str(entry.get(field)), "warn") for field in applied]
    return section("Corrections manuelles", items)
