"""Orchestrate the static knowledge base data build from audit artifacts.

One builder, several stores: the Todo List KB (knowledge_base/, the default) and the
Blender KB (knowledge_base_blender/, see kb_blender/builder.py) share the same guarantees —
upsert by id, drop protection, data.js for file:// — through a KbStore.
"""

import json
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import KB_DIR, ROOT_DIR
from .markdown_parser import extract_report_markdown, md_files_by_stem
from .normalizer import apply_overrides, is_test_artifact, load_all, load_overrides, normalize

_extract_report_markdown = extract_report_markdown

DATA_PATH = KB_DIR / "data.json"

PROMPT_SRC = ROOT_DIR / "prompts" / "evaluation_prompt.md"
PROMPT_DST = KB_DIR / "evaluation_prompt.md"


@dataclass(frozen=True)
class KbStore:
    """Where a KB lives and how its raw audits become entries.

    ``load_all()`` returns every normalized entry (full rebuild); ``load_one(path)`` one
    cr_*.json (upsert); ``after_write(entries)`` runs once data.json/data.js are written
    (e.g. publishing media next to them).
    """

    kb_dir: Path
    data_path: Path
    prompt_src: Path | None
    prompt_dst: Path | None
    load_all: Callable[[], list[dict[str, Any]]]
    load_one: Callable[[Path], dict[str, Any]]
    source_label: str = "cr_audits/"
    after_write: Callable[[list[dict[str, Any]]], None] | None = None


def _load_one_todo(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    report_markdown = extract_report_markdown(md_files_by_stem().get(path.stem))
    return apply_overrides(normalize(data, str(path), report_markdown), load_overrides())


def default_store() -> KbStore:
    """The Todo List KB. Module globals are read at call time (tests patch them)."""
    return KbStore(
        kb_dir=KB_DIR,
        data_path=DATA_PATH,
        prompt_src=PROMPT_SRC,
        prompt_dst=PROMPT_DST,
        load_all=lambda: load_all(),
        load_one=_load_one_todo,
    )


def write_embedded_js(entries: list[dict[str, Any]], store: KbStore | None = None) -> Path:
    """Write data.js next to data.json: the same entries (plus the evaluation prompt) as
    a classic script setting ``window.__HEXA_KB__``. It is what makes index.html usable
    from file://, where browsers block fetch(). Always written together with data.json so
    the two never diverge."""
    store = store or default_store()
    prompt_path = (
        store.prompt_dst if store.prompt_dst and store.prompt_dst.exists() else store.prompt_src
    )
    prompt = (
        prompt_path.read_text(encoding="utf-8") if prompt_path and prompt_path.exists() else None
    )
    payload = json.dumps({"entries": entries, "prompt": prompt}, ensure_ascii=False)
    # "</" would close the <script> element if the payload ever held "</script>".
    payload = payload.replace("</", "<\\/")
    js_path = store.data_path.with_suffix(".js")
    js_path.write_text(f"window.__HEXA_KB__ = {payload};\n", encoding="utf-8")
    return js_path


class KnowledgeBaseShrinkError(RuntimeError):
    """A full rebuild would drop entries already published in data.json.

    data.json is versioned; cr_audits/ is NOT (see .gitignore). A raw report deleted,
    or produced on another machine, is therefore unrecoverable — and a plain rebuild
    would silently erase the published run that derived from it.
    """


def _published_entries(store: KbStore | None = None) -> list[dict[str, Any]]:
    """Entries currently in data.json ([] when absent/unreadable — no protection then)."""
    data_path = (store or default_store()).data_path
    if not data_path.exists():
        return []
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError) as exc:
        print(f"[WARN] data.json unreadable, drop protection disabled: {exc}", file=sys.stderr)
        return []


def _dropped_entries(
    entries: list[dict[str, Any]], store: KbStore | None = None
) -> list[dict[str, Any]]:
    """Published entries that the freshly scanned `entries` would no longer cover."""
    rebuilt_ids = {entry.get("id") for entry in entries}
    return [
        published
        for published in _published_entries(store)
        if published.get("id") and published["id"] not in rebuilt_ids
    ]


def _shrink_message(dropped: list[dict[str, Any]], source_label: str = "cr_audits/") -> str:
    listed = "\n".join(
        f"  - {entry['id']}  ({entry.get('model') or '?'} · "
        f"{entry.get('score_percentage')}% · {entry.get('admission_status') or '?'})"
        for entry in dropped
    )
    return (
        f"refusing to rebuild: {len(dropped)} published entries have no source in {source_label}\n"
        f"{listed}\n"
        f"{source_label} is gitignored, so these raw reports cannot be recovered from git.\n"
        "Options:\n"
        f"  - restore the missing cr_*.json (+ .md twin) into {source_label}, then rebuild\n"
        f"  - use --add {source_label}cr_<...>.json to upsert one audit without touching the others\n"
        "  - pass --allow-drop to accept the loss (review the git diff of data.json)"
    )


def _write(entries: list[dict[str, Any]], store: KbStore) -> None:
    store.kb_dir.mkdir(parents=True, exist_ok=True)
    store.data_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] {store.data_path}  ({len(entries)} entries)")
    print(f"[OK] {write_embedded_js(entries, store)}")
    if store.after_write:
        store.after_write(entries)


def build_knowledge_base(
    allow_drop: bool = False, store: KbStore | None = None
) -> list[dict[str, Any]]:
    """Rebuild data.json and return normalized entries.

    Refuses to write when the rebuild would drop already-published entries, unless
    ``allow_drop`` is set. See KnowledgeBaseShrinkError.
    """
    store = store or default_store()
    store.kb_dir.mkdir(parents=True, exist_ok=True)
    entries = store.load_all()
    if not entries:
        print("[WARN] no audit JSON found", file=sys.stderr)

    dropped = _dropped_entries(entries, store)
    if dropped:
        if not allow_drop:
            raise KnowledgeBaseShrinkError(_shrink_message(dropped, store.source_label))
        print(
            f"[WARN] --allow-drop: removing {len(dropped)} published entries "
            f"({', '.join(entry['id'] for entry in dropped)})",
            file=sys.stderr,
        )

    if store.prompt_src and store.prompt_dst:
        if store.prompt_src.exists():
            shutil.copy2(store.prompt_src, store.prompt_dst)
            print(f"[OK] {store.prompt_dst}")
        else:
            print(f"[WARN] prompt not found: {store.prompt_src}", file=sys.stderr)
    _write(entries, store)
    return entries


def upsert_entry(cr_json_path: str, store: KbStore | None = None) -> list[dict[str, Any]]:
    """Ingest ONE cr_*.json and upsert it into data.json by id, without rescanning the
    whole source tree. Overrides are applied so the entry matches a full rebuild."""
    store = store or default_store()
    path = Path(cr_json_path)
    entry = store.load_one(path)
    if is_test_artifact(entry):
        raise ValueError(f"{path.name} looks like a test artifact; refusing to add")

    # Lecture STRICTE : un data.json illisible doit arrêter l'upsert, pas être remplacé
    # par la seule entrée ajoutée (le garde-fou tolérant ne vaut que pour la reconstruction).
    entries = (
        json.loads(store.data_path.read_text(encoding="utf-8")) if store.data_path.exists() else []
    )
    entries = [e for e in entries if e.get("id") != entry["id"]]
    entries.append(entry)
    entries.sort(key=lambda e: e.get("audit_started_at", ""), reverse=True)

    print(f"[OK] upsert {entry['id']} -> {store.data_path}")
    _write(entries, store)
    return entries


def main(
    store: KbStore | None = None, description: str = "Build the audit knowledge base."
) -> None:
    import argparse

    store = store or default_store()
    parser = argparse.ArgumentParser(description=description)
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
        upsert_entry(args.add, store)
    else:
        try:
            build_knowledge_base(allow_drop=args.allow_drop, store=store)
        except KnowledgeBaseShrinkError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
