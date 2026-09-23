"""Magasin knowledge_base_blender/ : kb.builder + publication des visuels.

Les visuels (rendus, silhouettes, turntable, planches d'animation) sont copiés de
cr_audits_blender/<id>_media/ vers knowledge_base_blender/media/<id>/. On n'en supprime
jamais : comme les entrées (loi n°8), un visuel publié survit à la perte du rapport brut.
"""

import shutil
from typing import Any

from kb.builder import KbStore
from kb.builder import main as kb_main

from .constants import DATA_PATH, KB_DIR, MEDIA_DIR, PROMPT_DST, PROMPT_SRC, SCAN_DIRS
from .normalizer import load_all, load_one


def publish_media(entries: list[dict[str, Any]]) -> None:
    copied = missing = 0
    for entry in entries:
        for media in entry.get("media") or []:
            destination = MEDIA_DIR / entry["id"] / media["file"]
            if destination.exists():
                continue
            source = next(
                (
                    d / f"{entry['id']}_media" / media["file"]
                    for d in SCAN_DIRS
                    if (d / f"{entry['id']}_media" / media["file"]).exists()
                ),
                None,
            )
            if source is None:
                missing += 1
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1
    print(f"[OK] {MEDIA_DIR}  ({copied} visuels copiés, {missing} introuvables)")


def blender_store() -> KbStore:
    return KbStore(
        kb_dir=KB_DIR,
        data_path=DATA_PATH,
        prompt_src=PROMPT_SRC,
        prompt_dst=PROMPT_DST,
        load_all=load_all,
        load_one=load_one,
        source_label="cr_audits_blender/",
        after_write=publish_media,
    )


def main() -> None:
    kb_main(blender_store(), "Build the Blender benchmark knowledge base.")
