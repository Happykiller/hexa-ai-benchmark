"""Intégration réelle : Blender headless sur les livrables témoins (sautés sans Blender).

Rapides (--skip-render, ~10 s chacun) par défaut ; HEXA_BLENDER_SLOW=1 ajoute les rendus.
"""

import json

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from hexa.benches.blender.auditor.cli import cli
from hexa.benches.blender.auditor.runner import run_blender
from hexa.benches.blender.tests.conftest import slow_enabled


def _audit(deliverable_path, tmp_path, monkeypatch, *extra):
    out = tmp_path / "cr"
    monkeypatch.setenv("HEXA_BLENDER_AUDIT_OUTPUT_DIR", str(out))
    result = CliRunner().invoke(cli, ["analyze", str(deliverable_path), *extra])
    assert result.exit_code == 0, f"{result.exception!r}\n{result.output}"
    reports = sorted(out.glob("cr_*.json"))
    assert len(reports) == 1 and reports[0].with_suffix(".md").exists()
    return json.loads(reports[0].read_text(encoding="utf-8"))


def _caps(report):
    return [cap["id"] for cap in report["summary"]["score_caps"]]


def test_minimal_valid_passes_operationality_and_rig(
    blender_bin, deliverable, tmp_path, monkeypatch
):
    report = _audit(deliverable("minimal_valid"), tmp_path, monkeypatch, "--skip-render")
    buckets = report["summary"]["bucket_scores"]
    assert _caps(report) == []
    assert buckets["operationality"]["normalized_score"] == 18.0
    assert buckets["rig_animation"]["normalized_score"] == 18.0
    assert buckets["traceability"]["normalized_score"] == 10.0
    visual = [
        i for i in report["indicators"] if i["phase_number"] == 5 and i["step_number"] in (1, 3)
    ]
    assert visual and all(i["status"] == "SKIPPED" for i in visual if i["kind"] == "scored")


def test_build_failure_is_capped_at_40(blender_bin, deliverable, tmp_path, monkeypatch):
    report = _audit(deliverable("build_fails"), tmp_path, monkeypatch, "--skip-render")
    assert _caps(report) == ["build_failed"]
    assert "échec volontaire" in report["artifacts"]["build"]["error"]
    assert report["summary"]["percentage_net"] <= 40


def test_runtime_guard_catches_network_access(blender_bin, deliverable, tmp_path, monkeypatch):
    report = _audit(deliverable("sandbox_violation"), tmp_path, monkeypatch, "--skip-render")
    assert "sandbox_violation" in _caps(report)
    assert report["artifacts"]["build"]["violations"][0]["call"] == "socket.socket"
    # Contrôle statique contourné par l'import dynamique : c'est bien le garde-fou qui a vu.
    static_check = next(
        i for i in report["indicators"] if i["name"].startswith("Aucun import réseau")
    )
    assert static_check["status"] == "OK"


def test_missing_armature_is_capped_at_50(blender_bin, deliverable, tmp_path, monkeypatch):
    report = _audit(deliverable("no_armature"), tmp_path, monkeypatch, "--skip-render")
    assert _caps(report) == ["no_armature"]
    assert report["summary"]["percentage_net"] <= 50


@pytest.mark.skipif(not slow_enabled(), reason="rendus : HEXA_BLENDER_SLOW=1")
def test_full_audit_with_renders(blender_bin, deliverable, tmp_path, monkeypatch):
    report = _audit(deliverable("minimal_valid"), tmp_path, monkeypatch)
    iou = report["stats"]["iou"]
    assert all(value is not None and 0.2 < value < 0.8 for value in iou.values()), iou
    assert report["stats"]["palette_delta_e"] < 10  # passe albédo : couleurs de palette exactes
    files = {item["file"] for item in report["artifacts"]["media"]}
    assert {"concept_front.jpg", "view_front.jpg", "silhouette_side.png", "anim_walk.jpg"} <= files
    assert {"anim_idle.mp4", "anim_walk.mp4", "turntable.mp4"} <= files


@pytest.mark.skipif(not slow_enabled(), reason="rendus : HEXA_BLENDER_SLOW=1")
def test_normalized_render_is_deterministic(blender_bin, deliverable, tmp_path, spec):
    source = deliverable("minimal_valid")
    work = tmp_path / "work"
    work.mkdir()
    build = run_blender(
        blender_bin,
        "run_build.py",
        ["--build", str(source / "build.py"), "--out", str(work / "out"),
         "--save", str(work / "scene.blend"), "--glb", str(work / "m.glb"), "--log", str(work / "log.json")],
        work, 300,
    )  # fmt: skip
    assert build["status"] == "OK"
    pixels = []
    for run in ("a", "b"):
        result = run_blender(
            blender_bin,
            "render_views.py",
            ["--mode", "normalized", "--views", "front", "--out-dir", str(work / run),
             "--profile", json.dumps(spec["render"]), "--log", str(work / f"{run}.json")],
            work, 600, blend=work / "scene.blend",
        )  # fmt: skip
        assert result["status"] == "OK", result["stderr"]
        pixels.append(
            [np.asarray(Image.open(work / run / f"view_front_{v}.png")) for v in ("flat", "beauty")]
        )
    for first, second in zip(pixels[0], pixels[1], strict=True):
        assert np.array_equal(first, second)
