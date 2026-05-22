"""Orchestrate the static knowledge base data build from audit artifacts."""

import json
import sys
from typing import Any, Dict, List

from .constants import KB_DIR
from .markdown_parser import extract_report_markdown
from .normalizer import load_all

_extract_report_markdown = extract_report_markdown


def build_knowledge_base() -> List[Dict[str, Any]]:
    """Rebuild knowledge_base/data.json and return normalized entries."""
    KB_DIR.mkdir(exist_ok=True)
    entries = load_all()
    if not entries:
        print("[WARN] no audit JSON found", file=sys.stderr)

    data_path = KB_DIR / "data.json"
    data_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] {data_path}  ({len(entries)} entries)")
    return entries


def main() -> None:
    build_knowledge_base()
