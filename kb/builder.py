"""Orchestrate the static knowledge base data build from audit artifacts."""

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from .constants import KB_DIR, ROOT_DIR, SCAN_DIRS
from .markdown_parser import extract_report_markdown, md_files_by_stem
from .normalizer import apply_overrides, is_test_artifact, load_all, load_overrides, normalize

_extract_report_markdown = extract_report_markdown

DATA_PATH = KB_DIR / "data.json"

PROMPT_SRC = ROOT_DIR / "prompts" / "evaluation_prompt.md"
PROMPT_DST = KB_DIR / "evaluation_prompt.md"


class KnowledgeBaseShrinkError(RuntimeError):
    """A full rebuild would drop entries already published in data.json."""


def build_knowledge_base(force: bool = False) -> list[dict[str, Any]]:
    """Rebuild knowledge_base/data.json and return normalized entries.

    cr_audits/ is NOT versioned: most published entries may have no raw file on this
    machine. A full rebuild would then silently erase them from the KB. Unless ``force``
    is set, refuse to write when entries present in the current data.json would vanish
    (use ``--add`` to ingest a single new audit instead)."""
    KB_DIR.mkdir(exist_ok=True)
    entries = load_all()
    if not entries:
        print("[WARN] no audit JSON found", file=sys.stderr)

    if DATA_PATH.exists() and not force:
        existing = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        rebuilt_ids = {e.get("id") for e in entries}
        lost = sorted(e.get("id", "?") for e in existing if e.get("id") not in rebuilt_ids)
        if lost:
            preview = "\n  - ".join(lost[:10]) + ("\n  - …" if len(lost) > 10 else "")
            raise KnowledgeBaseShrinkError(
                f"full rebuild would drop {len(lost)} published entr(y/ies) whose raw "
                f"cr_*.json is absent from {', '.join(str(d) for d in SCAN_DIRS)}:\n  - "
                f"{preview}\nUse `--add cr_audits/<file>.json` to add one audit, or "
                "`--force` if dropping them is intended."
            )

    DATA_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] {DATA_PATH}  ({len(entries)} entries)")

    if PROMPT_SRC.exists():
        shutil.copy2(PROMPT_SRC, PROMPT_DST)
        print(f"[OK] {PROMPT_DST}")
    else:
        print(f"[WARN] prompt not found: {PROMPT_SRC}", file=sys.stderr)

    return entries


def upsert_entry(cr_json_path: str) -> list[dict[str, Any]]:
    """Ingest ONE cr_*.json and upsert it into data.json by id, without rescanning the
    whole cr_audits/ tree. Overrides are applied so the entry matches a full rebuild."""
    path = Path(cr_json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    report_markdown = extract_report_markdown(md_files_by_stem().get(path.stem))
    entry = apply_overrides(normalize(data, str(path), report_markdown), load_overrides())
    if is_test_artifact(entry):
        raise ValueError(f"{path.name} looks like a test artifact; refusing to add")

    entries = json.loads(DATA_PATH.read_text(encoding="utf-8")) if DATA_PATH.exists() else []
    entries = [e for e in entries if e.get("id") != entry["id"]]
    entries.append(entry)
    entries.sort(key=lambda e: e.get("audit_started_at", ""), reverse=True)

    KB_DIR.mkdir(exist_ok=True)
    DATA_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] upsert {entry['id']} -> {DATA_PATH} ({len(entries)} entries)")
    return entries


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build the audit knowledge base.")
    parser.add_argument(
        "--add",
        metavar="CR_JSON",
        help="Upsert a single cr_*.json into data.json (by id) instead of a full rebuild.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Full rebuild even if it drops published entries whose raw cr_*.json is absent.",
    )
    args = parser.parse_args()
    if args.add:
        upsert_entry(args.add)
        return
    try:
        build_knowledge_base(force=args.force)
    except KnowledgeBaseShrinkError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
