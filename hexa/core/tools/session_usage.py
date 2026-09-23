"""Mesure l'usage RÉEL (tokens, modèle, effort, durée) d'une session d'agent à partir de
son transcript, et le confronte aux valeurs auto-déclarées dans ``audit_trace.json``.

Pourquoi : le pilier Coût (12 % en scoring v2) est calculé à partir des tokens que
l'agent audité déclare lui-même (voir docs/KB/DAF/tracabilite-agent.md). Ce script donne
à l'opérateur la mesure indépendante qui permet de lever le doute avant publication.
Il ne modifie rien : il lit et rapporte. N'influence pas le scoring.

Formats reconnus (détection automatique, par ligne) :
- Claude Code : ``~/.claude/projects/<cwd-encodé>/<session>.jsonl`` (+ les transcripts de
  sous-agents ``<session>/subagents/*.jsonl``, inclus automatiquement). L'usage est porté
  par chaque message assistant ; un même ``message.id`` est journalisé une fois par bloc de
  contenu, on déduplique donc par id.
- Codex CLI : ``~/.codex/sessions/AAAA/MM/JJ/rollout-*.jsonl`` — événements ``token_count``
  cumulatifs (on garde le dernier ``total_token_usage``).

Usage :
    python3 -m hexa usage <transcript.jsonl> [--trace <livrable>/audit_trace.json]
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from hexa.core.engine import _compute_session_cost, _normalize_model_id
from hexa.core.engine.config import MODEL_PRICING

# Multiplicateurs officiels des écritures de cache (Anthropic), relatifs au prix d'input.
_CACHE_WRITE_MULT = {"5m": 1.25, "1h": 2.0}


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _session_files(path: Path) -> list[Path]:
    files = [path]
    sub = path.with_suffix("") / "subagents"
    if sub.is_dir():
        files.extend(sorted(sub.glob("*.jsonl")))
    return files


def measure(path: Path) -> dict[str, Any]:
    claude_msgs: dict[str, dict[str, Any]] = {}
    codex_total: dict[str, Any] | None = None
    models: set[str] = set()
    efforts: set[str] = set()
    first: datetime | None = None
    last: datetime | None = None
    user_prompts = 0

    for file in _session_files(path):
        for line in file.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(event.get("timestamp"))
            if ts:
                first = ts if first is None or ts < first else first
                last = ts if last is None or ts > last else last

            # --- Claude Code ---
            message = event.get("message")
            if event.get("type") == "assistant" and isinstance(message, dict):
                usage = message.get("usage")
                if isinstance(usage, dict):
                    key = message.get("id") or event.get("requestId") or event.get("uuid")
                    claude_msgs[str(key)] = usage  # last write wins (same usage per block)
                if message.get("model"):
                    models.add(str(message["model"]))
                if event.get("effort"):
                    efforts.add(str(event["effort"]))
            elif (
                event.get("type") == "user"
                and not event.get("isSidechain")
                and isinstance(message, dict)
                and isinstance(message.get("content"), str)
            ):
                user_prompts += 1  # human-typed turns (tool results are lists)

            # --- Codex CLI ---
            payload = event.get("payload")
            if isinstance(payload, dict):
                if payload.get("type") == "token_count":
                    info = payload.get("info") or {}
                    if isinstance(info.get("total_token_usage"), dict):
                        codex_total = info["total_token_usage"]
                if payload.get("model"):
                    models.add(str(payload["model"]))
                if payload.get("effort") or payload.get("reasoning_effort"):
                    efforts.add(str(payload.get("effort") or payload.get("reasoning_effort")))

    result: dict[str, Any] = {
        "transcript": str(path),
        "models": sorted(models),
        "efforts": sorted(efforts),
        "first_event": first.isoformat() if first else None,
        "last_event": last.isoformat() if last else None,
        "wall_time_seconds": round((last - first).total_seconds()) if first and last else None,
    }
    if claude_msgs:
        uncached = sum(int(u.get("input_tokens", 0) or 0) for u in claude_msgs.values())
        read = sum(int(u.get("cache_read_input_tokens", 0) or 0) for u in claude_msgs.values())
        write = sum(int(u.get("cache_creation_input_tokens", 0) or 0) for u in claude_msgs.values())
        w5m = sum(
            int((u.get("cache_creation") or {}).get("ephemeral_5m_input_tokens", 0) or 0)
            for u in claude_msgs.values()
        )
        w1h = sum(
            int((u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0) or 0)
            for u in claude_msgs.values()
        )
        out = sum(int(u.get("output_tokens", 0) or 0) for u in claude_msgs.values())
        result.update(
            {
                "format": "claude-code",
                "api_calls": len(claude_msgs),
                "user_prompts": user_prompts,
                # Mapped to the audit_trace.json contract: input INCLUDES cache.
                "total_input_tokens": uncached + read + write,
                "total_cached_input_tokens": read,
                "total_output_tokens": out,
                "cache_write_tokens": {"total": write, "5m": w5m, "1h": w1h},
            }
        )
    elif codex_total:
        result.update(
            {
                "format": "codex",
                "total_input_tokens": int(codex_total.get("input_tokens", 0) or 0),
                "total_cached_input_tokens": int(codex_total.get("cached_input_tokens", 0) or 0),
                "total_output_tokens": int(codex_total.get("output_tokens", 0) or 0),
                "cache_write_tokens": {
                    "total": int(codex_total.get("cache_write_input_tokens", 0) or 0)
                },
            }
        )
    else:
        result["format"] = "unknown"
    return result


def _with_costs(measured: dict[str, Any], model: str | None) -> dict[str, Any]:
    """Coût tel que l'auditeur le calcule (proxy, écritures de cache au prix d'input) et
    coût liste réel (écritures de cache 5m ×1.25 / 1h ×2)."""
    if "total_input_tokens" not in measured:
        return measured
    auditor_cost = _compute_session_cost(measured, model)
    measured["auditor_cost_usd"] = auditor_cost["cost_usd"]
    measured["pricing_key"] = auditor_cost["model_key"]
    pricing = MODEL_PRICING.get(_normalize_model_id(model) or "")
    writes = measured.get("cache_write_tokens") or {}
    if pricing and auditor_cost["cost_usd"] is not None and "5m" in writes:
        surcharge = sum(
            writes.get(kind, 0) / 1e6 * pricing["input"] * (mult - 1)
            for kind, mult in _CACHE_WRITE_MULT.items()
        )
        measured["list_price_cost_usd"] = round(auditor_cost["cost_usd"] + surcharge, 4)
    return measured


def compare(measured: dict[str, Any], trace_path: Path) -> dict[str, Any]:
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    summary = trace.get("summary") or {}
    meta = trace.get("meta") or {}
    rows = {}
    for key in (
        "total_input_tokens",
        "total_cached_input_tokens",
        "total_output_tokens",
        "total_wall_time_seconds",
    ):
        declared = summary.get(key)
        real = measured.get("wall_time_seconds" if key == "total_wall_time_seconds" else key)
        delta = (
            round((declared - real) / real * 100, 1)
            if isinstance(declared, (int, float)) and isinstance(real, (int, float)) and real
            else None
        )
        rows[key] = {"declared": declared, "measured": real, "delta_pct": delta}
    return {
        "declared_model": meta.get("model"),
        "declared_effort": meta.get("effort"),
        "fields": rows,
        "declared_cost_usd": _compute_session_cost(
            {k: summary.get(k) for k in rows}, meta.get("model")
        )["cost_usd"],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="hexa usage", description=__doc__.split("\n\n")[0])
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--trace", type=Path, help="audit_trace.json du livrable à confronter")
    args = parser.parse_args(argv)

    measured = measure(args.transcript)
    model = measured["models"][0] if measured.get("models") else None
    report: dict[str, Any] = {"measured": _with_costs(measured, model)}
    if args.trace:
        report["comparison"] = compare(measured, args.trace)
    print(json.dumps(report, indent=2, ensure_ascii=False))
