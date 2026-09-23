"""Visuels publiés avec le rapport : rendus composés sur fond clair, turntable MP4, planches
d'animation. Ré-encodés par Pillow : aucune métadonnée (temps de rendu, machine) ne fuit.
JPEG pour les images aplaties : elles sont versionnées dans sites/blender/media/."""

import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

BACKGROUND = (234, 234, 234)  # gris des vignettes de la planche
MAX_SHEET_WIDTH = 1280
JPEG_QUALITY = 85


def _flatten(path: Path) -> Image.Image:
    image = Image.open(path).convert("RGBA")
    canvas = Image.new("RGBA", image.size, (*BACKGROUND, 255))
    canvas.alpha_composite(image)
    return canvas.convert("RGB")


def save_view(source: Path, destination: Path, max_width: int = 640) -> Path:
    image = _flatten(source)
    if image.width > max_width:
        image = image.resize(
            (max_width, round(image.height * max_width / image.width)), Image.LANCZOS
        )
    image.save(destination, quality=JPEG_QUALITY, optimize=True)
    return destination


def contact_sheet(frames: list[Path], destination: Path) -> Path | None:
    if not frames:
        return None
    images = [_flatten(path) for path in frames]
    width = sum(image.width for image in images)
    sheet = Image.new("RGB", (width, max(image.height for image in images)), BACKGROUND)
    x = 0
    for image in images:
        sheet.paste(image, (x, 0))
        x += image.width
    if sheet.width > MAX_SHEET_WIDTH:
        sheet = sheet.resize(
            (MAX_SHEET_WIDTH, round(sheet.height * MAX_SHEET_WIDTH / sheet.width)), Image.LANCZOS
        )
    sheet.save(destination, quality=JPEG_QUALITY, optimize=True)
    return destination


def frames_video(frames_dir: Path, prefix: str, destination: Path, fps: float) -> dict[str, Any]:
    """Assemble <prefix>_###.png en MP4 h264 sur fond clair (ffmpeg requis, non noté)."""
    ffmpeg = shutil.which("ffmpeg")
    frames = sorted(frames_dir.glob(f"{prefix}_[0-9][0-9][0-9].png"))
    if not ffmpeg or not frames:
        return {"status": "SKIPPED", "error": "ffmpeg absent" if not ffmpeg else "aucune image"}
    width, height = Image.open(frames[0]).size
    color = "0x" + "".join(f"{c:02X}" for c in BACKGROUND)
    cmd = [
        ffmpeg, "-y", "-loglevel", "error", "-framerate", f"{fps:g}",
        "-i", str(frames_dir / f"{prefix}_%03d.png"),
        "-filter_complex", f"color=c={color}:s={width}x{height}[bg];[bg][0:v]overlay=shortest=1,format=yuv420p",
        "-c:v", "libx264", "-crf", "28", "-threads", "1", "-movflags", "+faststart",
        "-fflags", "+bitexact", "-flags:v", "+bitexact", str(destination),
    ]  # fmt: skip
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    if result.returncode != 0:
        return {"status": "KO", "error": result.stderr[-2000:]}
    return {"status": "OK", "path": str(destination)}


def turntable_video(frames_dir: Path, destination: Path, fps: int = 12) -> dict[str, Any]:
    return frames_video(frames_dir, "turntable", destination, fps)


def concept_view(concept: Path, box: list[int], destination: Path, height: int = 540) -> Path:
    """Vignette du turnaround (l'attendu), agrandie pour être lue à côté du rendu."""
    crop = Image.open(concept).convert("RGB").crop(tuple(box))
    width = round(crop.width * height / crop.height)
    crop.resize((width, height), Image.LANCZOS).save(
        destination, quality=JPEG_QUALITY, optimize=True
    )
    return destination


def evenly(frames: list[Path], count: int) -> list[Path]:
    if len(frames) <= count:
        return frames
    return [frames[round(index * (len(frames) - 1) / (count - 1))] for index in range(count)]
