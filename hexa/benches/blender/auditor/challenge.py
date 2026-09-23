"""Catalogue des défis : un dossier challenges/<id>/ = concept.png + enonce.md + spec.json."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CHALLENGES_DIR = Path(__file__).resolve().parent.parent / "challenges"
DEFAULT_CHALLENGE = "dreadhive_drone_mk1"


@dataclass(frozen=True)
class BlenderChallenge:
    id: str
    root: Path
    spec: dict[str, Any] = field(repr=False)

    @property
    def label(self) -> str:
        return self.spec["label"]

    @property
    def prompt_version(self) -> str:
        return self.spec["prompt_version"]

    @property
    def concept_path(self) -> Path:
        return self.root / self.spec["concept"]

    @property
    def enonce_path(self) -> Path:
        return self.root / self.spec["enonce"]


def load_challenge(challenge_id: str = DEFAULT_CHALLENGE) -> BlenderChallenge:
    root = CHALLENGES_DIR / challenge_id
    spec_path = root / "spec.json"
    if not spec_path.exists():
        known = ", ".join(sorted(p.name for p in CHALLENGES_DIR.iterdir() if p.is_dir()))
        raise ValueError(f"défi inconnu : {challenge_id} (connus : {known})")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    return BlenderChallenge(id=spec["id"], root=root, spec=spec)


def available_challenges() -> list[str]:
    return sorted(p.name for p in CHALLENGES_DIR.iterdir() if (p / "spec.json").exists())
