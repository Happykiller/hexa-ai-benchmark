"""Emplacements de la knowledge base Todo List."""

from pathlib import Path

from hexa.paths import cr_audits_dir, site_dir

KB_DIR = site_dir("todo")
DATA_PATH = KB_DIR / "data.json"
# Corrections manuelles suivies (model/effort auto-déclarés…), par id d'entrée, appliquées
# au-dessus des rapports bruts au build : le brut reste immuable.
OVERRIDES_PATH = KB_DIR / "overrides.json"
SCAN_DIRS = [cr_audits_dir("todo")]
PROMPT_SRC = Path(__file__).resolve().parent.parent / "enonce" / "evaluation_prompt.md"
PROMPT_DST = KB_DIR / "evaluation_prompt.md"
