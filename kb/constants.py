from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
KB_DIR = ROOT_DIR / "knowledge_base"

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
