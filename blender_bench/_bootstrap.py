"""Rend le noyau commun importable (`from engine import …`).

auditor/ utilise des imports « plats » (main.py est lancé en script) : on ajoute donc
auditor/ au sys.path, exactement comme scripts/session_usage.py.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
AUDITOR_DIR = ROOT_DIR / "auditor"

if str(AUDITOR_DIR) not in sys.path:
    sys.path.insert(0, str(AUDITOR_DIR))
