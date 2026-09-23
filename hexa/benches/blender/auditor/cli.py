"""Auditeur du benchmark Blender 3D.

    python3 -m hexa blender analyze runs/blender/livrables/<NOM> [--skip-render] [--keep-work]

Pipeline : contrôles statiques → rejeu de build.py (Blender headless, garde-fous) →
inspection du .blend → aller-retour glTF → rendus imposés → analyses → indicateurs →
score (noyau hexa/core/engine) → runs/blender/cr_audits/cr_<livrable>_<horodatage>.{json,md}.
"""

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from jinja2 import Environment, FileSystemLoader
from rich.console import Console
from rich.table import Table

from hexa.benches.blender.auditor import media
from hexa.benches.blender.auditor.analysis import Check
from hexa.benches.blender.auditor.analysis.bonus_malus import analyze_bonus_malus
from hexa.benches.blender.auditor.analysis.geometry import analyze_geometry
from hexa.benches.blender.auditor.analysis.imagery import analyze_imagery
from hexa.benches.blender.auditor.analysis.materials import analyze_materials
from hexa.benches.blender.auditor.analysis.operationality import analyze_operationality
from hexa.benches.blender.auditor.analysis.rig_animation import analyze_rig_animation
from hexa.benches.blender.auditor.bench_config import (
    BLENDER_BONUS_MALUS_CONFIG,
    BLENDER_SCORE_BUCKETS_B1,
    CEILING_RULE,
    PHASES,
    SCORING_MODEL,
    SCORING_VERSION,
)
from hexa.benches.blender.auditor.challenge import (
    DEFAULT_CHALLENGE,
    available_challenges,
    load_challenge,
)
from hexa.benches.blender.auditor.emit import cap_reasons, emit_checks
from hexa.benches.blender.auditor.runner import blender_version, resolve_blender, run_blender
from hexa.benches.blender.auditor.static_checks import analyze_static
from hexa.core.engine import (
    TraceabilityValidator,
    _append_indicator,
    _build_trace_metrics,
    _finalize_audit_db,
    _md_cell,
    emit_cost_indicators,
    emit_trace_indicators,
)
from hexa.paths import cr_audits_dir

console = Console()
COPY_IGNORE = shutil.ignore_patterns(
    ".git", "__pycache__", "node_modules", "*.blend1", "audit_report_*.md"
)


def _log(message: str) -> None:
    console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim] {message}")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _runner_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key] for key in ("script", "status", "exit_code", "timed_out", "seconds")
    } | {
        "stderr_tail": result["stderr"][-1500:],
    }


class Pipeline:
    """Étapes Blender d'un audit ; chaque résultat brut est conservé pour le rapport."""

    def __init__(self, blender: str, workdir: Path, spec: dict[str, Any]):
        self.blender = blender
        self.workdir = workdir
        self.spec = spec
        self.runs: list[dict[str, Any]] = []

    def _run(
        self, script: str, args: list[str], timeout: str, blend: Path | None = None
    ) -> dict[str, Any]:
        result = run_blender(
            self.blender,
            script,
            args,
            self.workdir,
            self.spec["timeouts_s"][timeout],
            blend=blend,
            threads=self.spec["render"]["threads"],
        )
        self.runs.append(_runner_summary(result))
        return result

    def build(self, source: Path) -> dict[str, Any]:
        log = self.workdir / "build_log.json"
        result = self._run(
            "run_build.py",
            [
                "--build", str(source / "build.py"),
                "--out", str(self.workdir / "out"),
                "--save", str(self.workdir / "scene.blend"),
                "--glb", str(self.workdir / "model.glb"),
                "--log", str(log),
            ],
            "build",
        )  # fmt: skip
        data = _read_json(log) or {"build_status": "KO"}
        if result["timed_out"]:
            data.update(
                build_status="KO",
                exported=False,
                error=f"timeout ({self.spec['timeouts_s']['build']} s)",
            )
        elif result["exit_code"] != 0 and not data.get("error"):
            data["runner_error"] = (
                f"Blender exit_code={result['exit_code']}: {result['stderr'][-500:]}"
            )
        return data

    def inspect(self) -> dict[str, Any] | None:
        out = self.workdir / "inspection.json"
        self._run(
            "inspect_scene.py",
            ["--out", str(out), "--bone-pattern", self.spec["limbs"]["bone_pattern"]],
            "inspect",
            blend=self.workdir / "scene.blend",
        )
        return _read_json(out)

    def reimport(self) -> dict[str, Any]:
        out = self.workdir / "reimport.json"
        result = self._run(
            "reimport_gltf.py",
            ["--glb", str(self.workdir / "model.glb"), "--out", str(out)],
            "reimport",
        )
        return _read_json(out) or {
            "status": "KO",
            "error": f"réimport interrompu (exit_code={result['exit_code']})",
        }

    def render(self, mode: str, actions: list[str] | None = None) -> dict[str, Any]:
        log = self.workdir / f"render_{mode}.json"
        args = [
            "--mode", mode,
            "--out-dir", str(self.workdir / "renders"),
            "--profile", json.dumps(self.spec["render"]),
            "--log", str(log),
        ]  # fmt: skip
        if actions:
            args += ["--actions", ",".join(actions)]
        result = self._run("render_views.py", args, "render", blend=self.workdir / "scene.blend")
        data = _read_json(log) or {}
        if result["status"] != "OK":
            data["error"] = (
                data.get("error")
                or f"rendu {mode} en échec (exit_code={result['exit_code']}, timeout={result['timed_out']})"
            )
        return data


def _skipped(checks: list[Check], reason: str) -> list[Check]:
    for check in checks:
        if check.kind == "scored":
            check.status = "SKIPPED"
            check.ratio = 0.0
            check.remarks = reason
    return checks


def _publish_media(
    workdir: Path,
    media_dir: Path,
    spec: dict[str, Any],
    overlays: dict[str, Any],
    concept: Path,
    animation_log: dict[str, Any],
) -> list[dict[str, str]]:
    """Par vue : l'attendu (vignette du turnaround), le rendu, la silhouette superposée.
    Puis le turntable et, par action, une vidéo à vitesse réelle et une planche d'images."""
    renders = workdir / "renders"
    items: list[dict[str, str]] = []
    if not renders.exists():
        return items
    media_dir.mkdir(parents=True, exist_ok=True)
    labels = {"front": "FACE", "side": "PROFIL", "back": "DOS"}
    for view_id, view in spec["turnaround"]["views"].items():
        label = labels[view_id]
        if not view.get("source"):
            media.concept_view(concept, view["box_px"], media_dir / f"concept_{view_id}.jpg")
            items.append(
                {
                    "kind": "image",
                    "file": f"concept_{view_id}.jpg",
                    "label": f"Attendu {label} (turnaround)",
                }
            )
        source = renders / f"view_{view['camera']}_beauty.png"
        if source.exists():
            media.save_view(source, media_dir / f"view_{view_id}.jpg")
            items.append(
                {"kind": "image", "file": f"view_{view_id}.jpg", "label": f"Rendu {label}"}
            )
        overlay = (overlays.get(view_id) or {}).get("overlay")
        if overlay and Path(overlay).exists():
            shutil.copy2(overlay, media_dir / f"silhouette_{view_id}.png")
            items.append(
                {
                    "kind": "image",
                    "file": f"silhouette_{view_id}.png",
                    "label": f"Silhouette {label} (ambre : concept seul, bleu : rendu seul)",
                }
            )
    video = media.turntable_video(renders, media_dir / "turntable.mp4")
    if video["status"] == "OK":
        items.append({"kind": "video", "file": "turntable.mp4", "label": "Turntable 360°"})
    settings = spec["render"]["animation"]
    for action, info in (animation_log.get("actions") or {}).items():
        video = media.frames_video(
            renders, f"anim_{action}", media_dir / f"anim_{action}.mp4", info["fps"]
        )
        if video["status"] == "OK":
            items.append(
                {
                    "kind": "video",
                    "file": f"anim_{action}.mp4",
                    "label": f"Animation « {action} » ({info['duration_s']:g} s)",
                }
            )
        frames = sorted(renders.glob(f"anim_{action}_[0-9][0-9][0-9].png"))
        sheet = media.contact_sheet(
            media.evenly(frames, settings["sheet_frames"]), media_dir / f"anim_{action}.jpg"
        )
        if sheet:
            items.append(
                {
                    "kind": "sheet",
                    "file": f"anim_{action}.jpg",
                    "label": f"Action « {action} » (images clés)",
                }
            )
    return items


def _actions_to_render(inspection: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    """Actions requises d'abord, puis les actions supplémentaires qui animent le squelette."""
    required = list(spec["animations"]["required"])
    names = [a["name"] for a in inspection.get("actions", []) if a.get("targets_pose_bones")]
    ordered = [name for name in required if name in names] + sorted(set(names) - set(required))
    return ordered[: spec["render"]["animation"]["max_actions"]]


def _stats(
    inspection: dict[str, Any] | None,
    build: dict[str, Any],
    glb_mb: float | None,
    imagery: dict[str, Any],
) -> dict[str, Any]:
    inspection = inspection or {}
    meshes = inspection.get("meshes", [])
    armatures = inspection.get("armatures") or []
    return {
        "triangles": sum(mesh.get("tris", 0) for mesh in meshes),
        "meshes": len(meshes),
        "materials": len(inspection.get("materials", [])),
        "bones": max((len(arm["bones"]) for arm in armatures), default=0),
        "actions": [action["name"] for action in inspection.get("actions", [])],
        "build_seconds": build.get("build_seconds"),
        "glb_mb": glb_mb,
        "height_m": inspection.get("height"),
        "iou": {
            view: (result or {}).get("iou")
            for view, result in (imagery.get("silhouettes") or {}).items()
        },
        "palette_delta_e": (imagery.get("palette") or {}).get("mean_delta_e"),
    }


@click.group()
def cli() -> None:
    """Auditeur du benchmark Blender 3D (hexa-ai-benchmark)."""


@cli.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--challenge",
    default=DEFAULT_CHALLENGE,
    show_default=True,
    type=click.Choice(available_challenges()),
)
@click.option(
    "--skip-render",
    is_flag=True,
    help="Pas de rendus (itération rapide) : phase 5 en SKIPPED, score non publiable",
)
@click.option(
    "--keep-work", is_flag=True, help="Conserver le dossier de travail (scène, GLB, rendus, JSON)"
)
@click.option(
    "--reuse-work",
    type=click.Path(exists=True, file_okay=False),
    help="Réutiliser un dossier de travail (--keep-work) sans relancer Blender",
)
@click.option(
    "--blender",
    "blender_bin",
    default=None,
    help="Binaire Blender (défaut : $HEXA_BLENDER_BIN, PATH, ~/.local/bin/blender45)",
)
def analyze(
    path: str,
    challenge: str,
    skip_render: bool,
    keep_work: bool,
    reuse_work: str | None,
    blender_bin: str | None,
) -> None:
    """Audite un livrable Blender (dossier contenant build.py)."""
    target = Path(path).resolve()
    defi = load_challenge(challenge)
    spec = defi.spec
    started = datetime.now()
    audit_db: dict[str, Any] = {
        "meta": {
            "benchmark": "blender",
            "challenge": defi.id,
            "challenge_label": defi.label,
            "expected_prompt_version": defi.prompt_version,
            "target_path": str(target),
            "audit_started_at": started.isoformat(),
            "scoring_model": SCORING_MODEL,
            "scoring_version": SCORING_VERSION,
            "skip_render": skip_render,
            "render_profile": spec["render"],
            "score_cap_reasons": [],
        },
        "phases": [],
        "indicators": [],
        "points": [],
        "artifacts": {},
        "stats": {},
    }
    _log(f"[bold]Audit Blender[/bold] {target.name} — défi {defi.id}")

    static = analyze_static(target)
    blender = resolve_blender(blender_bin)
    audit_db["meta"]["blender_version"] = blender_version(blender) if blender else None
    workdir = (
        Path(reuse_work).resolve() if reuse_work else Path(tempfile.mkdtemp(prefix="hexa_blender_"))
    )
    pipeline = Pipeline(blender or "", workdir, spec)
    build: dict[str, Any] = {"build_status": "KO"}
    inspection = reimport = None

    if reuse_work:
        _log(f"Réutilisation de {workdir}")
        build = _read_json(workdir / "build_log.json") or build
        inspection = _read_json(workdir / "inspection.json")
        reimport = _read_json(workdir / "reimport.json")
    elif blender is None:
        build["runner_error"] = "Blender introuvable (--blender ou $HEXA_BLENDER_BIN)"
    elif static["build_present"]:
        source = workdir / "livrable"
        shutil.copytree(target, source, ignore=COPY_IGNORE)
        _log("Rejeu de build.py…")
        build = pipeline.build(source)
        _log(
            f"  build={build.get('build_status')} en {build.get('build_seconds')} s; export={build.get('exported')}"
        )
        if build.get("saved"):
            _log("Inspection de la scène…")
            inspection = pipeline.inspect()
        if build.get("exported"):
            _log("Aller-retour glTF…")
            reimport = pipeline.reimport()
    else:
        build["error"] = "build.py absent"

    glb = workdir / "model.glb"
    glb_mb = round(glb.stat().st_size / 1e6, 3) if glb.exists() else None

    render_logs: dict[str, Any] = {}
    renderable = (workdir / "scene.blend").exists() and inspection is not None
    if renderable and not skip_render and not (reuse_work and (workdir / "renders").exists()):
        for mode in ("normalized", "turntable", "animation"):
            _log(f"Rendu {mode}…")
            actions = _actions_to_render(inspection, spec)
            render_logs[mode] = pipeline.render(mode, actions if mode == "animation" else None)

    timestamp = started.strftime("%Y%m%d_%H%M%S")
    output_dir = Path(os.environ.get("HEXA_BLENDER_AUDIT_OUTPUT_DIR") or cr_audits_dir("blender"))
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"cr_{target.name}_{timestamp}"
    overlays_dir = workdir / "overlays"

    checks = analyze_operationality(static, build, reimport, glb_mb, spec)
    checks += analyze_geometry(inspection or {}, spec)
    imagery_checks, imagery = analyze_imagery(
        workdir / "renders", defi.concept_path, spec, overlays_dir
    )
    if skip_render or not renderable:
        reason = (
            "rendus désactivés (--skip-render)" if skip_render else "rien à rendre (build en échec)"
        )
        imagery_checks = _skipped(imagery_checks, reason) if skip_render else imagery_checks
    materials_checks = analyze_materials(inspection or {}, spec)
    checks += imagery_checks[:3] + materials_checks + imagery_checks[3:]
    checks += analyze_rig_animation(inspection or {}, spec)
    emit_checks(audit_db, checks)

    traceability = TraceabilityValidator(str(target)).validate()
    trace_metrics = _build_trace_metrics(traceability)
    emit_trace_indicators(audit_db, traceability, trace_metrics)
    declared = ((traceability.get("data") or {}).get("meta") or {}).get("prompt_version")
    _append_indicator(
        audit_db, 3, PHASES[3], 3, "Conformité à l'énoncé", "Version du prompt déclarée",
        declared == defi.prompt_version,
        f"déclarée={declared}; attendue={defi.prompt_version}",
        kind="measured", measured_value=declared,
    )  # fmt: skip
    audit_db["meta"]["cost"] = emit_cost_indicators(audit_db, trace_metrics)
    emit_checks(audit_db, analyze_bonus_malus(inspection, static, glb_mb, spec))

    audit_db["meta"]["score_cap_reasons"] = cap_reasons(build, reimport, inspection, spec)
    audit_db["phases"].sort(key=lambda phase: phase["number"])
    _finalize_audit_db(
        audit_db,
        SCORING_VERSION,
        buckets=BLENDER_SCORE_BUCKETS_B1,
        bonus_malus_config=BLENDER_BONUS_MALUS_CONFIG,
        ceiling_rule=CEILING_RULE,
    )

    media_dir = output_dir / f"{stem}_media"
    media_items = _publish_media(
        workdir,
        media_dir,
        spec,
        imagery.get("silhouettes") or {},
        defi.concept_path,
        render_logs.get("animation") or _read_json(workdir / "render_animation.json") or {},
    )
    audit_db["artifacts"] = {
        "static": static,
        "build": build,
        "inspection": inspection,
        "reimport": reimport,
        "imagery": imagery,
        "renders": render_logs,
        "blender_runs": pipeline.runs,
        "traceability": traceability,
        "trace_metrics": trace_metrics,
        "media": [item | {"path": f"{media_dir.name}/{item['file']}"} for item in media_items],
        "workdir": str(workdir) if keep_work or reuse_work else None,
    }
    audit_db["stats"] = _stats(inspection, build, glb_mb, imagery)
    audit_db["meta"]["audit_finished_at"] = datetime.now().isoformat()

    json_path = output_dir / f"{stem}.json"
    json_path.write_text(
        json.dumps(audit_db, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")))
    env.filters["md_cell"] = _md_cell
    report = env.get_template("report_blender.md").render(audit_data=audit_db)
    md_path = output_dir / f"{stem}.md"
    md_path.write_text(report, encoding="utf-8")
    try:
        (target / f"audit_report_{timestamp}.md").write_text(report, encoding="utf-8")
    except OSError as exc:
        _log(f"[yellow]Copie du rapport dans le livrable impossible : {exc}[/yellow]")

    if not keep_work and not reuse_work:
        shutil.rmtree(workdir, ignore_errors=True)
    elif keep_work:
        _log(f"Dossier de travail conservé : {workdir}")
    _print_summary(audit_db, json_path, md_path)


def _print_summary(audit_db: dict[str, Any], json_path: Path, md_path: Path) -> None:
    summary = audit_db["summary"]
    table = Table(title="Score par pilier")
    table.add_column("Pilier")
    table.add_column("Score", justify="right")
    table.add_column("Poids", justify="right")
    for bucket in summary["bucket_scores"].values():
        table.add_row(bucket["label"], f"{bucket['normalized_score']:.2f}", str(bucket["weight"]))
    console.print(table)
    for cap in summary["score_caps"]:
        console.print(f"[red]Cap {cap['id']} ({cap['max_percentage']} %)[/red] : {cap['reason']}")
    console.print(
        f"[bold]Score final : {summary['percentage_net']} %[/bold] "
        f"(base {summary['normalized_base_score']}/100, brut {summary['raw_percentage_net']} %)"
    )
    console.print(f"[dim]{json_path}\n{md_path}[/dim]")
