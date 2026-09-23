"""Constantes communes aux knowledge bases (tous benchmarks)."""

from hexa.paths import repo_relative  # noqa: F401 — ré-export

ADMISSION_THRESHOLD = 60.0

# Remarques d'indicateur qui signalent un constat à remonter dans la synthèse du rapport.
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
