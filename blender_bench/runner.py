"""Lancement de Blender en mode headless pour les scripts de blender_bench/bpy_scripts/."""

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

BPY_SCRIPTS = Path(__file__).resolve().parent / "bpy_scripts"
DEFAULT_BLENDER = Path.home() / ".local" / "bin" / "blender45"


def resolve_blender(explicit: str | None = None) -> str | None:
    """--blender > $HEXA_BLENDER_BIN > `blender` du PATH > ~/.local/bin/blender45."""
    for candidate in (explicit, os.environ.get("HEXA_BLENDER_BIN"), shutil.which("blender")):
        if candidate and Path(candidate).exists():
            return str(candidate)
    return str(DEFAULT_BLENDER) if DEFAULT_BLENDER.exists() else None


def blender_version(blender: str) -> str | None:
    try:
        out = subprocess.run(
            [blender, "--version"], capture_output=True, text=True, timeout=60, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    first = next((line for line in out.splitlines() if line.startswith("Blender")), "")
    return first.replace("Blender", "").strip() or None


def _minimal_env(workdir: Path) -> dict[str, str]:
    """Environnement réduit : rien de l'utilisateur, HOME et TMP dans le dossier de travail."""
    home = workdir / "home"
    tmp = workdir / "tmp"
    for directory in (home, tmp):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "LANG": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "BLENDER_USER_CONFIG": str(home / "config"),
        "BLENDER_USER_SCRIPTS": str(home / "scripts"),
        "BLENDER_USER_DATAFILES": str(home / "datafiles"),
    }


def run_blender(
    blender: str,
    script: str,
    args: list[str],
    workdir: Path,
    timeout: float,
    blend: Path | None = None,
    threads: int = 8,
) -> dict[str, Any]:
    """Exécute `script` dans Blender ; tue tout le groupe de processus en cas de timeout."""
    cmd = [blender, "-b"]
    if blend is not None:
        cmd.append(str(blend))
    cmd += [
        "--factory-startup",
        "-noaudio",
        "-t",
        str(threads),
        "--python-exit-code",
        "1",
        "--python",
        str(BPY_SCRIPTS / script),
        "--",
        *args,
    ]
    started = time.perf_counter()
    process = subprocess.Popen(
        cmd,
        cwd=workdir,
        env=_minimal_env(workdir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
    return {
        "script": script,
        "status": "OK" if process.returncode == 0 and not timed_out else "KO",
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "seconds": round(time.perf_counter() - started, 2),
        "stdout": stdout[-8000:],
        "stderr": stderr[-8000:],
    }
