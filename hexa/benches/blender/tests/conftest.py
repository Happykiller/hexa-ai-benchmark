import copy
import json
import os
import shutil
from pathlib import Path

import pytest

from hexa.benches.blender.auditor.challenge import load_challenge
from hexa.benches.blender.auditor.runner import resolve_blender

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def spec() -> dict:
    return load_challenge().spec


@pytest.fixture
def inspection() -> dict:
    """Inspection réelle (figée) du livrable témoin minimal_valid ; copie modifiable."""
    data = json.loads((FIXTURES / "inspection" / "minimal_valid.json").read_text(encoding="utf-8"))
    return copy.deepcopy(data)


@pytest.fixture(scope="session")
def blender_bin() -> str:
    binary = resolve_blender(None)
    if binary is None:
        pytest.skip("Blender introuvable (HEXA_BLENDER_BIN)")
    return binary


@pytest.fixture
def deliverable(tmp_path):
    """Copie un livrable témoin dans tmp_path : l'audit y écrit son audit_report_*.md."""

    def _copy(name: str) -> Path:
        target = tmp_path / name
        shutil.copytree(FIXTURES / name, target)
        return target

    return _copy


def slow_enabled() -> bool:
    return os.environ.get("HEXA_BLENDER_SLOW") == "1"
