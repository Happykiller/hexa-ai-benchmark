from typing import Any

from hexa.core.kb.cards import (  # noqa: F401 — ré-exports historiques
    bool_item,
    first_trace_finding,
    fmt_score,
    item,
    section,
    section_cost,
    section_overrides,
    section_report,
    section_trace_diagnostic,
    status_item,
    trace_indicator_label,
    trace_indicator_tooltip,
)


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
