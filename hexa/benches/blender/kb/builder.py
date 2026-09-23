"""Magasin de la knowledge base Blender (sites/blender/) + publication des visuels.

Les visuels (rendus, silhouettes, turntable, animations) sont copiés de
runs/blender/cr_audits/<id>_media/ vers sites/blender/media/<id>/. On n'en supprime
jamais : comme les entrées (loi n°8), un visuel publié survit à la perte du rapport brut.
"""

import shutil
from typing import Any

from PIL import Image

from hexa.core.kb.store import KbStore

from .constants import (
    CHALLENGES_DIR,
    DATA_PATH,
    KB_DIR,
    MEDIA_DIR,
    PROMPT_DST,
    PROMPT_SRC,
    SCAN_DIRS,
)
from .normalizer import load_all, load_one


def _publish_challenge_concept(challenge: str | None) -> int:
    """Copie (en JPEG) la planche du défi dans sites/blender/challenges/<id>/."""
    destination = KB_DIR / "challenges" / str(challenge) / "concept.jpg"
    source = CHALLENGES_DIR / str(challenge) / "concept.png"
    if destination.exists() or not source.exists():
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.open(source).convert("RGB").save(destination, quality=88, optimize=True)
    return 1


def publish_media(entries: list[dict[str, Any]]) -> None:
    copied = missing = 0
    for entry in entries:
        for media in entry.get("media") or []:
            if media.get("shared"):
                copied += _publish_challenge_concept(entry.get("challenge"))
                continue
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
        source_label="runs/blender/cr_audits/",
        after_write=publish_media,
    )
