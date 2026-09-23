"""Barème b1 de bout en bout (noyau engine) et contrôles statiques."""

from engine import _finalize_audit_db

from blender_bench.analysis import Check
from blender_bench.bench_config import (
    BLENDER_BONUS_MALUS_CONFIG,
    BLENDER_SCORE_BUCKETS_B1,
    CEILING_RULE,
    SCORING_VERSION,
)
from blender_bench.emit import cap_reasons, emit_checks
from blender_bench.static_checks import analyze_static


def _db():
    return {"meta": {"score_cap_reasons": []}, "phases": [], "indicators": [], "points": []}


def _finalize(db):
    _finalize_audit_db(
        db,
        SCORING_VERSION,
        buckets=BLENDER_SCORE_BUCKETS_B1,
        bonus_malus_config=BLENDER_BONUS_MALUS_CONFIG,
        ceiling_rule=CEILING_RULE,
    )
    return db["summary"]


def test_perfect_pillars_reach_100():
    db = _db()
    emit_checks(db, [Check(phase, 1, "étape", f"p{phase}", 1.0, 3) for phase in (1, 2, 3, 5, 6, 7)])
    summary = _finalize(db)
    assert summary["percentage_net"] == 100.0
    assert summary["scoring_version"] == "b1"
    assert set(summary["bucket_scores"]) == set(BLENDER_SCORE_BUCKETS_B1)


def test_half_visual_pillar_costs_twelve_points():
    db = _db()
    checks = [Check(phase, 1, "étape", f"p{phase}", 1.0, 3) for phase in (1, 2, 3, 6, 7)]
    checks.append(Check(5, 1, "étape", "visuel", 0.5, 3))
    emit_checks(db, checks)
    assert _finalize(db)["percentage_net"] == 88.0


def test_malus_applies_and_measured_do_not_count():
    db = _db()
    checks = [Check(phase, 1, "étape", f"p{phase}", 1.0, 3) for phase in (1, 2, 3, 5, 6, 7)]
    checks.append(Check(4, 2, "Écarts", "malus", 1.0, weight=3, polarity="negative"))
    checks.append(Check(2, 9, "Mesures", "mesure", kind="measured", measured_value=42))
    emit_checks(db, checks)
    assert _finalize(db)["percentage_net"] == 97.0


def test_caps(spec):
    ok_build = {"build_status": "OK", "exported": True}
    assert cap_reasons({"build_status": "KO"}, None, None, spec)[0]["id"] == "build_failed"
    violation = {"build_status": "OK", "exported": False, "violations": [{"call": "socket.socket"}]}
    assert [c["id"] for c in cap_reasons(violation, None, None, spec)] == [
        "sandbox_violation",
        "build_failed",
    ]
    assert (
        cap_reasons(ok_build, {"status": "KO"}, {"armatures": []}, spec)[0]["id"]
        == "gltf_not_reimportable"
    )
    ids = [c["id"] for c in cap_reasons(ok_build, {"status": "OK"}, {"armatures": []}, spec)]
    assert ids == ["no_armature"]
    static = {
        "armatures": [{"bones": []}],
        "actions": [{"name": "idle", "motion": {"max_displacement_ratio": 0.0}}],
    }
    assert cap_reasons(ok_build, {"status": "OK"}, static, spec)[0]["id"] == "no_real_animation"


def test_capped_score(spec):
    db = _db()
    emit_checks(db, [Check(phase, 1, "étape", f"p{phase}", 1.0, 3) for phase in (1, 2, 3, 5, 6, 7)])
    db["meta"]["score_cap_reasons"] = cap_reasons(
        {"build_status": "OK", "exported": True}, {"status": "OK"}, {"armatures": []}, spec
    )
    summary = _finalize(db)
    assert summary["percentage_net"] == 50.0 and summary["score_capped"]


def test_static_checks_detect_forbidden_code(tmp_path):
    (tmp_path / "build.py").write_text(
        "import bpy\nimport subprocess\npath = '/home/moi/tex.png'\n", encoding="utf-8"
    )
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "net.py").write_text("import os\nos.system('ls')\n", encoding="utf-8")
    result = analyze_static(tmp_path)
    assert result["build_present"] and not result["readme_present"]
    hits = [hit for found in result["forbidden"].values() for hit in found]
    assert {(hit["file"], hit["line"]) for hit in hits} == {("build.py", 2), ("lib/net.py", 2)}
    assert result["absolute_paths"][0]["line"] == 3
