"""Orchestrate the static knowledge base data build from audit artifacts."""

import json
import shutil
import sys
from pathlib import Path
from typing import Any

from .constants import KB_DIR, ROOT_DIR
from .markdown_parser import extract_report_markdown, md_files_by_stem
from .normalizer import apply_overrides, is_test_artifact, load_all, load_overrides, normalize

_extract_report_markdown = extract_report_markdown

DATA_PATH = KB_DIR / "data.json"

PROMPT_SRC = ROOT_DIR / "prompts" / "evaluation_prompt.md"
PROMPT_DST = KB_DIR / "evaluation_prompt.md"


class KnowledgeBaseShrinkError(RuntimeError):
    """A full rebuild would drop entries already published in data.json.

    data.json is versioned; cr_audits/ is NOT (see .gitignore). A raw report deleted,
    or produced on another machine, is therefore unrecoverable — and a plain rebuild
    would silently erase the published run that derived from it.
    """


def _published_entries() -> list[dict[str, Any]]:
    """Entries currently in data.json ([] when absent/unreadable — no protection then)."""
    if not DATA_PATH.exists():
        return []
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError) as exc:
        print(f"[WARN] data.json unreadable, drop protection disabled: {exc}", file=sys.stderr)
        return []


def _dropped_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Published entries that the freshly scanned `entries` would no longer cover."""
    rebuilt_ids = {entry.get("id") for entry in entries}
    return [
        published
        for published in _published_entries()
        if published.get("id") and published["id"] not in rebuilt_ids
    ]


def _shrink_message(dropped: list[dict[str, Any]]) -> str:
    listed = "\n".join(
        f"  - {entry['id']}  ({entry.get('model') or '?'} · "
        f"{entry.get('score_percentage')}% · {entry.get('admission_status') or '?'})"
        for entry in dropped
    )
    return (
        f"refusing to rebuild: {len(dropped)} published entries have no source in cr_audits/\n"
        f"{listed}\n"
        "cr_audits/ is gitignored, so these raw reports cannot be recovered from git.\n"
        "Options:\n"
        "  - restore the missing cr_*.json (+ .md twin) into cr_audits/, then rebuild\n"
        "  - use --add cr_audits/cr_<...>.json to upsert one audit without touching the others\n"
        "  - pass --allow-drop to accept the loss (review `git diff knowledge_base/data.json`)"
    )


def build_knowledge_base(allow_drop: bool = False) -> list[dict[str, Any]]:
    """Rebuild knowledge_base/data.json and return normalized entries.

    Refuses to write when the rebuild would drop already-published entries, unless
    ``allow_drop`` is set. See KnowledgeBaseShrinkError.
    """
    KB_DIR.mkdir(exist_ok=True)
    entries = load_all()
    if not entries:
        print("[WARN] no audit JSON found", file=sys.stderr)

    dropped = _dropped_entries(entries)
    if dropped:
        if not allow_drop:
            raise KnowledgeBaseShrinkError(_shrink_message(dropped))
        print(
            f"[WARN] --allow-drop: removing {len(dropped)} published entries "
            f"({', '.join(entry['id'] for entry in dropped)})",
            file=sys.stderr,
        )

    data_path = KB_DIR / "data.json"
    data_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] {data_path}  ({len(entries)} entries)")

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
        "--allow-drop",
        action="store_true",
        help="Allow a full rebuild to delete published entries whose cr_*.json is gone.",
    )
    args = parser.parse_args()
    if args.add:
        upsert_entry(args.add)
    else:
        try:
            build_knowledge_base(allow_drop=args.allow_drop)
        except KnowledgeBaseShrinkError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
