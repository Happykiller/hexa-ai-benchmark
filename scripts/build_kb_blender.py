#!/usr/bin/env python3
"""CLI de la knowledge base du benchmark Blender (knowledge_base_blender/).

python3 scripts/build_kb_blender.py --add cr_audits_blender/cr_<...>.json
python3 scripts/build_kb_blender.py            # reconstruction complète
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from kb_blender.builder import main

if __name__ == "__main__":
    main()
