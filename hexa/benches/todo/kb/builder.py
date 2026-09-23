"""Magasin de la knowledge base Todo List (sites/todo/).

Les globales du module sont lues à l'appel (default_store) : les tests les remplacent.
"""

import json
from pathlib import Path
from typing import Any

from hexa.benches.todo.kb.constants import DATA_PATH, KB_DIR, PROMPT_DST, PROMPT_SRC, SCAN_DIRS
from hexa.benches.todo.kb.normalizer import apply_overrides, load_all, load_overrides, normalize
from hexa.core.kb import store as core_store
from hexa.core.kb.markdown_parser import extract_report_markdown, md_files_by_stem
from hexa.core.kb.store import KbStore, KnowledgeBaseShrinkError  # noqa: F401 — ré-exports

_extract_report_markdown = extract_report_markdown


def _load_one(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    report_markdown = extract_report_markdown(md_files_by_stem(SCAN_DIRS).get(path.stem))
    return apply_overrides(normalize(data, str(path), report_markdown), load_overrides())


def default_store() -> KbStore:
    return KbStore(
        kb_dir=KB_DIR,
        data_path=DATA_PATH,
        prompt_src=PROMPT_SRC,
        prompt_dst=PROMPT_DST,
        load_all=lambda: load_all(),
        load_one=_load_one,
        source_label="runs/todo/cr_audits/",
    )


def write_embedded_js(entries: list[dict[str, Any]], store: KbStore | None = None) -> Path:
    return core_store.write_embedded_js(entries, store or default_store())


def build_knowledge_base(
    allow_drop: bool = False, store: KbStore | None = None
) -> list[dict[str, Any]]:
    return core_store.build_knowledge_base(store or default_store(), allow_drop)


def upsert_entry(cr_json_path: str, store: KbStore | None = None) -> list[dict[str, Any]]:
    return core_store.upsert_entry(store or default_store(), cr_json_path)
