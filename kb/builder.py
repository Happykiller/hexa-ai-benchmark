"""Orchestrate the static knowledge base data build from audit artifacts."""

import json
import shutil
import sys
from typing import Any, Dict, List

from .constants import KB_DIR, ROOT_DIR
from .markdown_parser import extract_report_markdown
from .normalizer import load_all

_extract_report_markdown = extract_report_markdown

PROMPT_SRC = ROOT_DIR / "prompts" / "evaluation_prompt.md"
PROMPT_DST = KB_DIR / "evaluation_prompt.md"


def build_knowledge_base() -> List[Dict[str, Any]]:
    """Rebuild knowledge_base/data.json and return normalized entries."""
    KB_DIR.mkdir(exist_ok=True)
    entries = load_all()
    if not entries:
        print("[WARN] no audit JSON found", file=sys.stderr)

    data_path = KB_DIR / "data.json"
    data_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] {data_path}  ({len(entries)} entries)")

    if PROMPT_SRC.exists():
        shutil.copy2(PROMPT_SRC, PROMPT_DST)
        print(f"[OK] {PROMPT_DST}")
    else:
        print(f"[WARN] prompt not found: {PROMPT_SRC}", file=sys.stderr)

    return entries


def main() -> None:
    build_knowledge_base()
