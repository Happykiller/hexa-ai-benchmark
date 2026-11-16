"""Tous les chemins du dépôt, en un seul endroit.

runs/<bench>/livrables/   livrables soumis par les agents       (gitignoré)
runs/<bench>/cr_audits/   rapports bruts, source immuable       (gitignoré)
sites/<bench>/            knowledge base publiée (data + web)   (versionné)
"""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT_DIR / "runs"
SITES_DIR = ROOT_DIR / "sites"
BENCHES = ("todo", "blender")


def livrables_dir(bench: str) -> Path:
    return RUNS_DIR / bench / "livrables"


def cr_audits_dir(bench: str) -> Path:
    return RUNS_DIR / bench / "cr_audits"


def site_dir(bench: str) -> Path:
    return SITES_DIR / bench


def repo_relative(path: Path | str) -> str:
    """Chemin relatif au dépôt (POSIX) : aucune trace machine dans les données publiées.
    Retombe sur le chemin absolu hors du dépôt."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def portable_path(path: Path | str) -> str:
    """Chemin d'un livrable tel qu'on le publie : jamais de préfixe machine.

    Contrairement à ``repo_relative`` il ne résout rien (un chemin relatif tapé par
    l'opérateur reste tel quel) et il reconnaît le dépôt cloné sur une autre machine :
    tout ce qui précède ``<nom du dépôt>/`` est retiré."""
    text = str(path).replace("\\", "/")
    if not text.startswith("/"):
        return text
    marker = f"/{ROOT_DIR.name}/"
    if marker in text:
        return text.split(marker, 1)[1]
    return text
