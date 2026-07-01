from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
KB_DIR = ROOT_DIR / "knowledge_base"

# Tracked manual corrections (model/effort self-declared by the audited agent, etc.),
# keyed by entry id. Applied on top of the raw cr_audits data at KB build time so the
# raw audit output stays immutable. See kb/normalizer.py:_apply_overrides.
OVERRIDES_PATH = KB_DIR / "overrides.json"

SCAN_DIRS = [
    ROOT_DIR / "cr_audits",
    ROOT_DIR / "auditor" / "cr_audits",
]

ADMISSION_THRESHOLD = 60.0

FINDING_TOKENS = (
    "ko",
    "timed out",
    "timeout",
    "unauthorized",
    "forbidden",
    "error",
    "failed",
    "manquant",
    "absent",
    "detected=no",
    "value is not numeric",
)
