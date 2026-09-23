"""Point d'entrée unique : `python3 -m hexa <commande>`.

\b
    todo analyze <livrable>        auditer un livrable Todo List
    blender analyze <livrable>     auditer un livrable Blender 3D
    kb <bench> [--add CR_JSON]     publier dans la knowledge base d'un benchmark
    usage <transcript.jsonl>       mesurer l'usage réel d'une session d'agent
    migrate-layout                 déplacer les données d'une ancienne arborescence
"""

import shutil
import sys

import click

from hexa.benches.blender.auditor.cli import cli as blender_cli
from hexa.benches.todo.auditor.main import cli as todo_cli
from hexa.paths import BENCHES, ROOT_DIR, cr_audits_dir, livrables_dir, site_dir


@click.group(help=__doc__)
def cli() -> None:
    pass


cli.add_command(todo_cli, "todo")
cli.add_command(blender_cli, "blender")


def _store(bench: str):
    if bench == "blender":
        from hexa.benches.blender.kb.builder import blender_store

        return blender_store()
    from hexa.benches.todo.kb.builder import default_store

    return default_store()


@cli.command("kb")
@click.argument("bench", type=click.Choice(BENCHES))
@click.option(
    "--add", "cr_json", metavar="CR_JSON", help="Ajoute/remplace UN rapport (voie par défaut)."
)
@click.option(
    "--allow-drop", is_flag=True, help="Accepter qu'une reconstruction retire des entrées publiées."
)
def kb(bench: str, cr_json: str | None, allow_drop: bool) -> None:
    """Publie dans sites/<bench>/data.json (+ data.js). Sans --add : reconstruction complète."""
    from hexa.core.kb.store import KnowledgeBaseShrinkError, build_knowledge_base, upsert_entry

    store = _store(bench)
    if cr_json:
        upsert_entry(store, cr_json)
        return
    try:
        build_knowledge_base(store, allow_drop)
    except KnowledgeBaseShrinkError as exc:
        click.echo(f"[ERROR] {exc}", err=True)
        sys.exit(1)


@cli.command("usage", context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.pass_context
def usage(ctx: click.Context) -> None:
    """Usage réel (tokens, modèle, effort, durée) d'un transcript, confronté à audit_trace.json."""
    from hexa.core.tools.session_usage import main

    main(ctx.args)


# Ancienne arborescence (avant 2026-09-23) → nouvelle. Les données gitignorées ne suivent pas
# git : chaque machine lance cette commande une fois.
_LEGACY = {
    "livrables": livrables_dir("todo"),
    "cr_audits": cr_audits_dir("todo"),
    "livrables_blender": livrables_dir("blender"),
    "cr_audits_blender": cr_audits_dir("blender"),
    "knowledge_base": site_dir("todo"),
    "knowledge_base_blender": site_dir("blender"),
}


@cli.command("migrate-layout")
@click.option("--dry-run", is_flag=True)
def migrate_layout(dry_run: bool) -> None:
    """Déplace livrables/, cr_audits/… d'une ancienne arborescence vers runs/ et sites/."""
    moved = 0
    for old_name, new in _LEGACY.items():
        old = ROOT_DIR / old_name
        if not old.exists() or not any(old.iterdir()):
            continue
        if new.exists() and any(new.iterdir()):
            click.echo(
                f"[SKIP] {old_name}/ : {new.relative_to(ROOT_DIR)} n'est pas vide, fusion manuelle"
            )
            continue
        click.echo(f"[{'DRY' if dry_run else 'MOVE'}] {old_name}/ → {new.relative_to(ROOT_DIR)}/")
        if not dry_run:
            new.parent.mkdir(parents=True, exist_ok=True)
            if new.exists():
                new.rmdir()
            shutil.move(str(old), str(new))
        moved += 1
    click.echo(f"{moved} dossier(s) {'à déplacer' if dry_run else 'déplacé(s)'}.")
