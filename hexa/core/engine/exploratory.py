"""KPI exploratoires : mesurés et publiés, JAMAIS notés.

C'est le sas d'entrée de tout nouveau KPI (docs/KB/DAF/kpi-exploratoires.md) : il est
d'abord émis ici, en ``kind="measured"``, dans une phase qu'aucun pilier ne sélectionne.
Il ne peut donc pas changer un score, et les runs publiés avant son arrivée restent
valides — ils affichent simplement « non mesuré ». Un KPI n'est promu en indicateur noté
que dans une nouvelle version de barème (v4, b2…), une fois calibré sur plusieurs runs.

``KPI_REVISION`` est écrit dans ``meta.kpi_revision`` : il dit quel jeu de KPI un rapport
a pu mesurer. L'incrémenter à chaque ajout ou changement de définition.
"""

from pathlib import Path
from typing import Any

from hexa.core.engine.indicators import _append_indicator

EXPLORATORY_PHASE = 8
EXPLORATORY_PHASE_LABEL = "KPI exploratoires (mesurés, non notés)"
KPI_REVISION = "2026-11.2"  # .2 : avis de sécurité npm (Todo)

SESSION_STEP = (1, "Session : vraisemblance et mesure externe")

# En dessous, les tokens déclarés ne couvrent même pas la relecture du contexte à chaque
# appel d'outil : sous-déclaration probable (compteurs sans le cache, ou partiels).
# Repère tiré des runs publiés : 1 100 à 2 000 pour les déclarations douteuses, 20 000 à
# 130 000 pour celles recoupées avec le transcript. Ce n'est pas un seuil de notation.
TOKENS_PER_TOOL_CALL_FLOOR = 3000


def emit_exploratory(
    audit_db: dict[str, Any],
    step: tuple[int, str],
    name: str,
    value: Any,
    remarks: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    """Ajoute un KPI exploratoire. ``value=None`` = non mesurable sur ce livrable."""
    audit_db.setdefault("meta", {})["kpi_revision"] = KPI_REVISION
    _append_indicator(
        audit_db,
        EXPLORATORY_PHASE,
        EXPLORATORY_PHASE_LABEL,
        step[0],
        step[1],
        name,
        False,
        remarks or ("non mesurable" if value is None else ""),
        kind="measured",
        measured_value=value,
        details=details or {},
    )


def _ratio(numerator: Any, denominator: Any, digits: int = 2) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)):
        return None
    if not denominator:
        return None
    return round(numerator / denominator, digits)


def measure_transcript(transcript: str | Path | None) -> dict[str, Any] | None:
    """Usage réel de la session lu dans son transcript (None si absent ou illisible)."""
    if not transcript:
        return None
    # Import tardif : session_usage dépend du noyau, pas l'inverse.
    from hexa.core.tools.session_usage import _with_costs, measure

    path = Path(transcript)
    if not path.is_file():
        return {"error": f"transcript introuvable : {path.name}"}
    try:
        measured = measure(path)
    except (OSError, ValueError) as exc:
        return {"error": f"transcript illisible : {exc}"}
    if "total_input_tokens" not in measured:
        return {"error": "format de transcript non reconnu"}
    model = measured["models"][0] if measured.get("models") else None
    measured = _with_costs(measured, model)
    # Jamais de chemin machine dans un rapport publié.
    measured.pop("transcript", None)
    return measured


def emit_session_kpis(
    audit_db: dict[str, Any],
    trace_metrics: dict[str, Any],
    cost_info: dict[str, Any],
    transcript_usage: dict[str, Any] | None = None,
) -> None:
    """KPI de session communs à tous les benchmarks.

    Les tokens d'``audit_trace.json`` sont déclarés par l'agent (loi n°4) : ces KPI disent
    si la déclaration est vraisemblable et, quand l'opérateur fournit le transcript, ce
    que la session a réellement consommé.
    """
    tokens = cost_info.get("total_tokens")
    inp = cost_info.get("input_tokens")
    cached = cost_info.get("cached_input_tokens")
    tools = trace_metrics.get("total_tool_calls")
    wall = trace_metrics.get("total_wall_time_seconds")

    per_tool = _ratio(tokens, tools, 0)
    if per_tool is None:
        verdict = "tokens ou appels d'outils non déclarés"
    elif per_tool < TOKENS_PER_TOOL_CALL_FLOOR:
        verdict = (
            f"déclaration douteuse : sous le repère de {TOKENS_PER_TOOL_CALL_FLOOR} "
            "tokens par appel (cache probablement non compté)"
        )
    else:
        verdict = "déclaration vraisemblable"
    emit_exploratory(audit_db, SESSION_STEP, "Tokens déclarés par appel d'outil", per_tool, verdict)
    emit_exploratory(
        audit_db,
        SESSION_STEP,
        "Part de cache dans l'entrée déclarée (%)",
        _ratio((cached or 0) * 100, inp, 1) if inp else None,
        "cache non déclaré : les tokens sont comptés au plein tarif" if inp and not cached else "",
    )
    emit_exploratory(
        audit_db,
        SESSION_STEP,
        "Appels d'outils par minute",
        _ratio((tools or 0) * 60, wall, 2) if tools else None,
    )

    usage = transcript_usage or {}
    if not transcript_usage:
        note = "transcript non fourni (--transcript)"
    elif usage.get("error"):
        note = usage["error"]
    else:
        note = f"transcript {usage.get('format')}"
    measured_tokens = None
    if "total_input_tokens" in usage:
        measured_tokens = usage["total_input_tokens"] + usage.get("total_output_tokens", 0)
    emit_exploratory(
        audit_db,
        SESSION_STEP,
        "Tokens mesurés dans le transcript (in+out)",
        measured_tokens,
        note,
        details=usage,
    )
    delta = None
    if measured_tokens and isinstance(tokens, (int, float)):
        delta = round((tokens - measured_tokens) / measured_tokens * 100, 1)
    emit_exploratory(
        audit_db,
        SESSION_STEP,
        "Écart déclaré / mesuré sur les tokens (%)",
        delta,
        "négatif = l'agent déclare moins que ce qu'il a consommé" if delta is not None else note,
    )
    emit_exploratory(
        audit_db,
        SESSION_STEP,
        "Coût mesuré dans le transcript ($)",
        usage.get("auditor_cost_usd"),
        f"modèle={usage.get('pricing_key')}" if usage.get("auditor_cost_usd") is not None else note,
    )
    emit_exploratory(
        audit_db,
        SESSION_STEP,
        "Durée mesurée dans le transcript (s)",
        usage.get("wall_time_seconds"),
        "" if usage.get("wall_time_seconds") is not None else note,
    )
    audit_db["meta"]["token_source"] = (
        "transcript" if measured_tokens else ("déclaré" if tokens is not None else "absent")
    )
