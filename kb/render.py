import json
from typing import Any

from .markdown_parser import truncate


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


def section_scores(entry: dict[str, Any]) -> dict[str, Any] | None:
    labels = {
        "operationality": "Opérationnalité",
        "architecture": "Architecture",
        "quality": "Qualité logicielle",
        "traceability": "Traçabilité",
        "cost": "Coût & Efficience",  # scoring v2 only
    }
    items = []
    for key, label in labels.items():
        if key not in entry["bucket_scores"]:
            continue  # e.g. no cost pillar before scoring v2
        bucket = entry["bucket_scores"][key]
        norm = float(bucket.get("normalized_score", 0))
        weight = float(bucket.get("weight", 0))
        pct = round(norm / weight * 100) if weight else 0
        cls = "ok" if pct >= 70 else "warn" if pct >= 40 else "ko"
        items.append(item(label, f"{norm:.1f} / {weight} ({pct}%)", cls))
    if entry.get("score_capped"):
        caps = ", ".join(entry.get("score_caps") or [])
        tt_caps = (entry.get("_tooltips") or {}).get("score_caps")
        items.append(item("Cap appliqué", caps, "warn", tt_caps))
    items.append(
        item("Modèle scoring", entry["scoring_model"].replace("indicator_fibonacci_", "fib_"))
    )
    return section("Score détaillé", items)


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


def section_pipeline(entry: dict[str, Any]) -> dict[str, Any] | None:
    make_targets = entry.get("make_targets")
    if not make_targets:
        return None
    tooltips = (entry.get("_tooltips") or {}).get("make", {})
    items = [
        status_item(f"make {target}", status, tooltips.get(target))
        for target, status in make_targets.items()
    ]
    docker = entry.get("docker") or {}
    waited = f" ({docker['waited_s']}s)" if docker.get("waited_s") is not None else ""
    items.append(
        status_item(f"docker start{waited}", docker.get("status", "?"), tooltips.get("docker"))
    )
    return section("Pipeline", items)


def section_stats(entry: dict[str, Any]) -> dict[str, Any] | None:
    stats = entry.get("stats")
    if not stats:
        return None
    items = []
    if stats.get("files") is not None:
        items.append(item("Fichiers", f"{stats['files']} ({stats.get('ts_files')} .ts)"))
    if stats.get("lines") is not None:
        items.append(item("Lignes TS", str(stats["lines"])))
    if stats.get("test_files") is not None:
        items.append(item("Fichiers test", str(stats["test_files"])))
    tests_pass, tests_fail = stats.get("tests_pass") or 0, stats.get("tests_fail") or 0
    if tests_pass or tests_fail:
        value = f"{tests_pass} ✓" + (f" / {tests_fail} ✗" if tests_fail else "")
        items.append(item("Tests exécutés", value, "ko" if tests_fail else "ok"))
    coverage = stats.get("coverage")
    if coverage is not None:
        cls = "ok" if coverage >= 80 else "warn" if coverage >= 60 else "ko"
        items.append(item("Coverage", f"{coverage}%", cls))
    return section("Stats projet", items) if items else None


def section_checks(entry: dict[str, Any]) -> dict[str, Any] | None:
    hexa = entry.get("hexagonal") or {}
    auth = entry.get("auth_static") or {}
    injection = entry.get("injection") or {}
    dual_persistence = entry.get("dual_persistence") or {}
    tooltips = entry.get("_tooltips") or {}
    if not any([hexa, auth, injection, dual_persistence]):
        return None

    items = []
    if hexa:
        violations = hexa.get("violations", 0)
        rules = f"{hexa.get('rules_ok')}/{hexa.get('rules_total')} règles"
        value = rules + (f" ({violations} viol.)" if violations else "")
        items.append(
            item(
                "Hexagonal",
                value,
                "ok" if hexa.get("status") == "OK" else "ko",
                tooltips.get("hexa_violations"),
            )
        )
    if auth:
        items.extend(
            [
                bool_item("JWT library", auth.get("jwt")),
                bool_item("Auth mutations", auth.get("mutations")),
                bool_item(
                    "Auth guard",
                    auth.get("guard"),
                    None
                    if auth.get("guard")
                    else "Pattern attendu: isAuthenticated|authGuard|AuthGuard|verifyToken|@Authorized — non détecté dans src/",
                ),
                bool_item("Password hash", auth.get("hashing")),
            ]
        )
    if injection:
        items.extend(
            [
                bool_item(
                    "No direct new", injection.get("no_direct"), tooltips.get("inj_violations")
                ),
                bool_item("@injectable", injection.get("injectable")),
                bool_item("@inject param", injection.get("inject")),
                bool_item("Ctor inject", injection.get("ctor_deps")),
            ]
        )
    if dual_persistence:
        items.extend(
            [
                bool_item("Mongoose installé", dual_persistence.get("mongoose")),
                bool_item("SQL ORM installé", dual_persistence.get("sql_orm")),
                bool_item("Mongo (tasks)", dual_persistence.get("mongoose_tasks")),
                bool_item("SQL (users)", dual_persistence.get("sql_users")),
                bool_item("Adapters séparés", dual_persistence.get("adapters")),
            ]
        )
    return section("Checks statiques", items)


def section_e2e(entry: dict[str, Any]) -> dict[str, Any] | None:
    tooltips = (entry.get("_tooltips") or {}).get("e2e", {})
    if entry.get("skip_dynamic"):
        return section("E2E", [item("Phase dynamique", "ignorée (--skip-dynamic)", "skip")])

    e2e_steps = entry.get("e2e_steps") or {}
    auth_e2e_steps = entry.get("auth_e2e_steps") or {}
    if not e2e_steps and not auth_e2e_steps:
        docker = entry.get("docker") or {}
        make_tooltips = (entry.get("_tooltips") or {}).get("make", {})
        docker_status = docker.get("status") or "NON_EXECUTE"
        cls = "ok" if docker_status == "OK" else "ko" if docker_status == "KO" else "skip"
        detail = make_tooltips.get("docker")
        label = "Runtime GraphQL" if docker_status == "KO" else "Scénario E2E"
        value = docker_status if docker_status != "NON_EXECUTE" else "non exécuté"
        return section("E2E", [item(label, value, cls, detail)])

    items = [bool_item(step, ok, tooltips.get(step)) for step, ok in e2e_steps.items()]
    items.extend(
        [
            bool_item(step.replace("Auth: ", ""), ok, tooltips.get(step))
            for step, ok in auth_e2e_steps.items()
        ]
    )
    return section("E2E", items) if items else None


def section_trace(entry: dict[str, Any]) -> dict[str, Any] | None:
    trace_metrics = entry.get("trace_metrics")
    if not trace_metrics or trace_metrics.get("turns") is None:
        return None
    items = []
    if entry.get("agent"):
        items.append(item("Livrable", str(entry["agent"])))
    if entry.get("prompt_version"):
        items.append(item("Prompt version", str(entry["prompt_version"])))
    if trace_metrics.get("phases") is not None:
        items.append(item("Phases", str(trace_metrics["phases"])))
    turns = trace_metrics.get("turns")
    if turns is not None:
        cls = "ok" if 5 <= turns <= 15 else "warn" if 2 <= turns <= 25 else "ko"
        items.append(item("Turns", str(int(turns)), cls))
    tools = trace_metrics.get("tools")
    if tools is not None:
        cls = "ok" if 20 <= tools <= 60 else "warn" if 10 <= tools <= 100 else "ko"
        items.append(item("Tool calls", str(int(tools)), cls))
    wall_s = trace_metrics.get("wall_s")
    if wall_s is not None:
        cls = "ok" if 600 <= wall_s <= 1800 else "warn" if 300 <= wall_s <= 3600 else "ko"
        items.append(item("Wall time", f"{round(wall_s / 60, 1)} min", cls))
    if trace_metrics.get("errors"):
        tt_trace = (entry.get("_tooltips") or {}).get("trace_errors")
        items.append(item("Erreurs trace", str(trace_metrics["errors"]), "ko", tt_trace))
    return section("Trace session", items)


def section_bonuses(entry: dict[str, Any]) -> dict[str, Any] | None:
    bonuses = entry.get("bonuses") or []
    maluses = entry.get("maluses") or []
    if not bonuses and not maluses:
        return None
    items = [
        item(
            bonus["reason"][:50],
            "✓ obtenu" if bonus["ok"] else "absent",
            "ok" if bonus["ok"] else "na",
        )
        for bonus in bonuses
    ]
    items.extend(
        [
            item(
                malus["reason"][:50],
                "! détecté" if malus["detected"] else "✓ non détecté",
                "ko" if malus["detected"] else "ok",
            )
            for malus in maluses
        ]
    )
    return section("Bonus / Malus", items)


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


SECTION_EXTRACTORS = [
    section_scores,
    section_overrides,
    section_cost,
    section_trace_diagnostic,
    section_pipeline,
    section_stats,
    section_checks,
    section_e2e,
    section_trace,
    section_bonuses,
    section_report,
]


def build_sections(entry: dict[str, Any]) -> list[dict[str, Any]]:
    sections = [
        section_data
        for extractor in SECTION_EXTRACTORS
        for section_data in [extractor(entry)]
        if section_data
    ]
    if entry["scoring_model"] == "legacy":
        sections.append(
            section(
                "Note",
                [
                    item("Format", "legacy — checks détaillés non disponibles", "na"),
                    item("Conseil", "Relancer l'audit pour le détail complet", "na"),
                ],
            )
        )
    return sections
