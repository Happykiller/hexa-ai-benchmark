#!/usr/bin/env python3
"""CLI wrapper for the static audit knowledge base builder."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from kb.builder import main

if __name__ == "__main__":
    main()
