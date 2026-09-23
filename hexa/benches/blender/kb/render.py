"""Cartes de détail d'une entrée Blender : générées depuis les indicateurs de chaque phase,
plus les cartes génériques de kb/render (traçabilité, coût, corrections, rapport)."""

from typing import Any

from hexa.core.kb.cards import (
    item,
    section,
    section_cost,
    section_overrides,
    section_report,
    section_trace_diagnostic,
)

PHASE_CARDS = (1, 2, 5, 7, 4)


def _cls(ratio: float) -> str:
    return "ok" if ratio >= 0.999 else "warn" if ratio > 0 else "ko"


def section_scores(entry: dict[str, Any]) -> dict[str, Any]:
    items = []
    for bucket in (entry.get("bucket_scores") or {}).values():
        norm, weight = float(bucket["normalized_score"]), float(bucket["weight"])
        pct = round(norm / weight * 100) if weight else 0
        cls = "ok" if pct >= 70 else "warn" if pct >= 40 else "ko"
        items.append(item(bucket.get("label", "?"), f"{norm:.1f} / {weight:g} ({pct}%)", cls))
    if entry.get("score_caps"):
        items.append(item("Cap appliqué", ", ".join(entry["score_caps"]), "warn"))
    if entry.get("skip_render"):
        items.append(item("Rendus", "désactivés (--skip-render)", "warn"))
    items.append(item("Défi", entry.get("challenge_label") or entry.get("challenge") or "?"))
    items.append(item("Modèle scoring", entry.get("scoring_model", "?")))
    return section("Score détaillé", items)


def section_phase(entry: dict[str, Any], phase: dict[str, Any]) -> dict[str, Any] | None:
    items = []
    for indicator in phase["indicators"]:
        if indicator["kind"] == "measured":
            items.append(
                item(
                    indicator["name"], str(indicator["measured_value"]), None, indicator["remarks"]
                )
            )
            continue
        max_score = indicator["max_score"] or 0
        score = indicator["score"] or 0
        if indicator["polarity"] == "negative":
            detected = score < 0
            items.append(
                item(
                    indicator["name"],
                    f"{score:g}" if detected else "—",
                    "ko" if detected else "ok",
                    indicator["remarks"],
                )
            )
            continue
        if indicator["status"] == "SKIPPED":
            items.append(item(indicator["name"], "non évalué", "skip", indicator["remarks"]))
            continue
        ratio = score / max_score if max_score else 0.0
        items.append(
            item(indicator["name"], f"{score:g} / {max_score:g}", _cls(ratio), indicator["remarks"])
        )
    return section(phase["label"], items) if items else None


def section_media(entry: dict[str, Any]) -> dict[str, Any] | None:
    stats = entry.get("blender") or {}
    iou = stats.get("iou") or {}
    if not stats:
        return None
    items = [
        item("Triangles", f"{stats.get('triangles') or 0:,}".replace(",", " ")),
        item(
            "Os / actions", f"{stats.get('bones')} / {', '.join(stats.get('actions') or []) or '—'}"
        ),
        item("Hauteur", f"{stats.get('height_m')} m"),
        item(
            "IoU FACE / PROFIL / DOS",
            " / ".join(str(iou.get(view, "—")) for view in ("front", "side", "back")),
        ),
        item("ΔE moyen (albédo → palette)", str(stats.get("palette_delta_e"))),
        item("Build", f"{stats.get('build_seconds')} s · GLB {stats.get('glb_mb')} Mo"),
    ]
    return section("Modèle", items)


def build_sections(entry: dict[str, Any]) -> list[dict[str, Any]]:
    phases = {phase["number"]: phase for phase in entry.get("phases_detail") or []}
    sections = [section_scores(entry), section_media(entry)]
    sections += [section_phase(entry, phases[number]) for number in PHASE_CARDS if number in phases]
    sections += [
        section_trace_diagnostic(entry),
        section_cost(entry),
        section_overrides(entry),
        section_report(entry),
    ]
    return [card for card in sections if card]
