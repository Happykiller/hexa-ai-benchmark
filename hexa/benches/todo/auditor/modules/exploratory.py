"""KPI exploratoires de la Todo List : mesurés, jamais notés.

Voir hexa/core/engine/exploratory.py pour la règle. Ces mesures cherchent ce que les
piliers saturés ne voient plus (qualité 13/13 sur tous les runs v2) : duplication, densité
de décisions, poids des dépendances, couverture de branches, latence et démarrage.
Ce sont des approximations lexicales, sans parseur TypeScript : comparables d'un livrable
à l'autre, pas des valeurs d'outil de référence.
"""

import json
import os
import re
import subprocess
from collections import Counter
from datetime import UTC, datetime
from typing import Any

import requests

from hexa.benches.todo.auditor.modules.static_analysis import EXCLUDED_DIRS
from hexa.core.engine.exploratory import emit_exploratory

CODE_STEP = (2, "Code : duplication, complexité, dépendances")
RUNTIME_STEP = (3, "Exécution : couverture de branches, latence, démarrage")
SUPPLY_STEP = (4, "Dépendances : avis de sécurité")

ADVISORY_API = "https://api.github.com/advisories/"

DUPLICATION_WINDOW = 6  # lignes consécutives identiques pour compter une duplication
_TEST_FILE = re.compile(r"(\.test\.|\.spec\.|/tests?/|/__tests__/|/e2e/)")
_NOISE_LINE = re.compile(r"^(import\b|export \* from|export \{[^}]*\} from|[{}()\[\];,]*$)")
_DECISION = re.compile(r"\b(?:if|for|while|case|catch)\b|&&|\|\||\?\?|\s\?\s")


def _source_files(target: str) -> list[str]:
    files = []
    for root, dirs, names in os.walk(target):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for name in names:
            if name.endswith((".ts", ".tsx")) and not name.endswith(".d.ts"):
                path = os.path.join(root, name)
                if not _TEST_FILE.search(path.replace("\\", "/")):
                    files.append(path)
    return sorted(files)


def _code_lines(path: str) -> list[str]:
    """Lignes de code utiles : sans blancs, commentaires, imports ni ponctuation seule."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            raw = handle.read()
    except OSError:
        return []
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)
    lines = []
    for line in raw.splitlines():
        line = re.sub(r"\s+", " ", line.split("//", 1)[0]).strip()
        if line and not _NOISE_LINE.match(line):
            lines.append(line)
    return lines


def measure_code(target: str) -> dict[str, Any]:
    per_file = {path: _code_lines(path) for path in _source_files(target)}
    total = sum(len(lines) for lines in per_file.values())
    if not total:
        return {"files": 0, "code_lines": 0}

    windows: Counter[tuple[str, ...]] = Counter()
    for lines in per_file.values():
        for i in range(len(lines) - DUPLICATION_WINDOW + 1):
            windows[tuple(lines[i : i + DUPLICATION_WINDOW])] += 1
    duplicated = 0
    for lines in per_file.values():
        marked = [False] * len(lines)
        for i in range(len(lines) - DUPLICATION_WINDOW + 1):
            if windows[tuple(lines[i : i + DUPLICATION_WINDOW])] > 1:
                marked[i : i + DUPLICATION_WINDOW] = [True] * DUPLICATION_WINDOW
        duplicated += sum(marked)

    decisions = sum(len(_DECISION.findall(line)) for lines in per_file.values() for line in lines)
    longest = max(per_file.items(), key=lambda item: len(item[1]))
    return {
        "files": len(per_file),
        "code_lines": total,
        "duplication_pct": round(duplicated / total * 100, 2),
        "decisions_per_100_lines": round(decisions / total * 100, 2),
        "longest_file_lines": len(longest[1]),
        "longest_file": os.path.relpath(longest[0], target).replace("\\", "/"),
    }


def measure_dependencies(target: str) -> dict[str, Any]:
    try:
        with open(os.path.join(target, "package.json"), encoding="utf-8") as handle:
            package = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(package, dict):
        return {}
    return {
        "runtime": len(package.get("dependencies") or {}),
        "dev": len(package.get("devDependencies") or {}),
    }


def measure_branch_coverage(target: str) -> float | None:
    try:
        with open(
            os.path.join(target, "coverage", "coverage-summary.json"), encoding="utf-8"
        ) as handle:
            pct = json.load(handle)["total"]["branches"]["pct"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return float(pct) if isinstance(pct, (int, float)) else None


def session_start_from_trace(traceability: dict[str, Any]) -> datetime | None:
    """Début de session déclaré : le plus ancien ``start_time`` des phases d'audit_trace.json."""
    data = traceability.get("data") if isinstance(traceability, dict) else None
    phases = data.get("phases") if isinstance(data, dict) else None
    starts = []
    for phase in phases if isinstance(phases, list) else []:
        try:
            start = datetime.fromisoformat(str(phase.get("start_time", "")).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        starts.append(start if start.tzinfo else start.replace(tzinfo=UTC))
    return min(starts) if starts else None


def _npm_audit(target: str, *extra: str) -> dict[str, Any] | None:
    try:
        result = subprocess.run(
            ["npm", "audit", "--json", *extra],
            cwd=target,
            capture_output=True,
            text=True,
            timeout=90,
        )
        data = json.loads(result.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return data if isinstance(data.get("vulnerabilities"), dict) else None


def _severe_advisories(audit: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Avis high/critical DISTINCTS, par identifiant GHSA. ``npm audit`` compte aussi chaque
    paquet qui dépend d'un paquet vulnérable : 5 « high » peuvent être 2 failles."""
    advisories: dict[str, dict[str, Any]] = {}
    for vulnerability in audit["vulnerabilities"].values():
        for via in vulnerability.get("via") or []:
            if isinstance(via, dict) and via.get("severity") in ("high", "critical"):
                ghsa = str(via.get("url", "")).rstrip("/").rsplit("/", 1)[-1]
                advisories[ghsa or via.get("title", "?")] = {
                    "package": via.get("name"),
                    "severity": via.get("severity"),
                    "title": via.get("title"),
                }
    return advisories


def _published_at(ghsa: str) -> datetime | None:
    try:
        response = requests.get(
            ADVISORY_API + ghsa, headers={"Accept": "application/vnd.github+json"}, timeout=10
        )
        published = response.json().get("published_at") if response.status_code == 200 else None
        return datetime.fromisoformat(published.replace("Z", "+00:00")) if published else None
    except (requests.RequestException, ValueError, AttributeError):
        return None


def measure_advisories(target: str, session_start: datetime | None) -> dict[str, Any]:
    """Avis de sécurité tels qu'un barème équitable les compterait.

    Le malus noté (4-2-8) compte les paquets signalés le jour de l'AUDIT, développement
    compris, en tout ou rien. Ici : avis distincts, part en dépendances d'exécution, et part
    déjà publiée quand l'agent a travaillé — un livrable ne doit pas être pénalisé pour une
    faille révélée après sa session (constat du 2026-11-16, docs/KB/DAF/kpi-exploratoires.md).
    """
    if not os.path.exists(os.path.join(target, "package-lock.json")):
        return {"error": "pas de package-lock.json"}
    full = _npm_audit(target)
    if full is None:
        return {"error": "npm audit indisponible (hors ligne ?)"}
    advisories = _severe_advisories(full)
    runtime_audit = _npm_audit(target, "--omit=dev")
    runtime = sorted(_severe_advisories(runtime_audit)) if runtime_audit is not None else None

    known_before: list[str] | None = [] if session_start else None
    for ghsa, advisory in advisories.items():
        published = _published_at(ghsa)
        advisory["published_at"] = published.isoformat() if published else None
        if known_before is None or published is None:
            known_before = None  # une date manque : on ne conclut pas à moitié
        elif published <= session_start:
            known_before.append(ghsa)
    return {
        "advisories": advisories,
        "distinct": len(advisories),
        "runtime": runtime,
        "known_before_session": known_before,
        "session_start": session_start.isoformat() if session_start else None,
        "npm_reported": {
            key: full.get("metadata", {}).get("vulnerabilities", {}).get(key)
            for key in ("high", "critical")
        },
    }


def _emit_advisories(audit_db: dict[str, Any], measures: dict[str, Any]) -> None:
    error = measures.get("error")
    ids = ", ".join(sorted(measures.get("advisories") or {})) or "aucun"
    reported = measures.get("npm_reported") or {}
    emit_exploratory(
        audit_db,
        SUPPLY_STEP,
        "Avis de sécurité high/critical distincts",
        measures.get("distinct"),
        error
        or f"{ids} ; npm signale {reported.get('high')} high et {reported.get('critical')} "
        "critical en comptant les paquets dépendants",
        details=measures,
    )
    runtime = measures.get("runtime")
    emit_exploratory(
        audit_db,
        SUPPLY_STEP,
        "dont en dépendances d'exécution",
        None if runtime is None else len(runtime),
        error or ("npm audit --omit=dev" if runtime is not None else "mesure indisponible"),
    )
    known = measures.get("known_before_session")
    emit_exploratory(
        audit_db,
        SUPPLY_STEP,
        "dont publiés avant la session de l'agent",
        None if known is None else len(known),
        error
        or (
            f"session du {measures['session_start'][:10]} ; "
            + "; ".join(
                f"{ghsa} publié le {(advisory.get('published_at') or '?')[:10]}"
                for ghsa, advisory in sorted(measures["advisories"].items())
            )
            if known is not None
            else "date de session ou de publication indisponible"
        ),
    )


def emit_todo_exploratory(
    audit_db: dict[str, Any],
    target: str,
    performance: dict[str, Any],
    docker_start: dict[str, Any],
    dynamic_ran: bool,
    session_start: datetime | None = None,
    check_advisories: bool = True,
) -> None:
    code = measure_code(target)
    emit_exploratory(
        audit_db,
        CODE_STEP,
        "Duplication du code source (%)",
        code.get("duplication_pct"),
        f"fenêtre de {DUPLICATION_WINDOW} lignes identiques, hors tests et imports ; "
        f"{code.get('code_lines', 0)} lignes utiles dans {code.get('files', 0)} fichiers",
        details=code,
    )
    emit_exploratory(
        audit_db,
        CODE_STEP,
        "Points de décision pour 100 lignes",
        code.get("decisions_per_100_lines"),
        "if / for / while / case / catch / && / || / ?? / ternaire (approximation lexicale)",
        details=code,
    )
    emit_exploratory(
        audit_db,
        CODE_STEP,
        "Plus long fichier source (lignes utiles)",
        code.get("longest_file_lines"),
        code.get("longest_file", ""),
        details=code,
    )
    deps = measure_dependencies(target)
    emit_exploratory(
        audit_db,
        CODE_STEP,
        "Dépendances d'exécution (package.json)",
        deps.get("runtime"),
        f"devDependencies={deps.get('dev')}" if deps else "package.json absent ou illisible",
        details=deps,
    )

    branches = measure_branch_coverage(target)
    emit_exploratory(
        audit_db,
        RUNTIME_STEP,
        "Couverture de branches (%)",
        branches,
        "coverage/coverage-summary.json (total.branches)"
        if branches is not None
        else "rapport json-summary absent",
    )
    measured_perf = dynamic_ran and bool(performance.get("p95_ms"))
    emit_exploratory(
        audit_db,
        RUNTIME_STEP,
        "Latence p95 de l'API (ms)",
        round(performance["p95_ms"], 2) if measured_perf else None,
        f"50 requêtes tasks séquentielles ; erreurs={performance.get('error_rate')} %"
        if measured_perf
        else "phase dynamique non exécutée",
    )
    waited = docker_start.get("waited_seconds")
    emit_exploratory(
        audit_db,
        RUNTIME_STEP,
        "Attente avant API saine après make start (s)",
        waited if docker_start.get("status") == "OK" else None,
        "pas de la boucle d'attente de l'auditeur, pas un chronomètre fin"
        if docker_start.get("status") == "OK"
        else "stack non démarrée",
    )
    if check_advisories:
        _emit_advisories(audit_db, measure_advisories(target, session_start))
