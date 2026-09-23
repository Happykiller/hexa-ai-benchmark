"""Contrôles statiques du livrable, avant tout lancement de Blender."""

import re
from pathlib import Path
from typing import Any

from blender_bench.bench_config import ABSOLUTE_PATH_PATTERN, FORBIDDEN_CODE_PATTERNS

README_MIN_CHARS = 400
IGNORED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}


def python_files(target: Path) -> list[Path]:
    return sorted(
        path
        for path in target.rglob("*.py")
        if not IGNORED_DIRS & set(path.relative_to(target).parts)
    )


def _scan(files: list[Path], target: Path, pattern: str) -> list[dict[str, Any]]:
    regex = re.compile(pattern, re.MULTILINE)
    hits = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in regex.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            hits.append(
                {
                    "file": path.relative_to(target).as_posix(),
                    "line": line,
                    "match": match.group(0).strip()[:120],
                }
            )
    return hits


def analyze_static(target: Path) -> dict[str, Any]:
    build = target / "build.py"
    readme = target / "README.md"
    files = python_files(target)
    readme_text = readme.read_text(encoding="utf-8", errors="replace") if readme.exists() else ""
    return {
        "build_present": build.is_file(),
        "readme_present": readme.is_file(),
        "readme_chars": len(readme_text.strip()),
        "trace_present": (target / "audit_trace.json").is_file(),
        "python_files": [path.relative_to(target).as_posix() for path in files],
        "forbidden": {
            label: _scan(files, target, pattern)
            for label, pattern in FORBIDDEN_CODE_PATTERNS.items()
        },
        "absolute_paths": _scan(files, target, ABSOLUTE_PATH_PATTERN),
    }
