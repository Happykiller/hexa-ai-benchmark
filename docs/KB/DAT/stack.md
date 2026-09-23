---
titre: Stack technique
type: dat
statut: actif
maj: 2026-09-23
---

# Stack technique

Le dépôt héberge **deux stacks distinctes** qui ne partagent aucun runtime. C'est volontaire :
l'auditeur doit pouvoir tourner sans Node, et le rendu web sans Python.

## Python — l'auditeur et le builder de KB

Déclaré dans `requirements.txt` et `pyproject.toml`.

- Cible **Python 3.11** (`[tool.ruff] target-version`).
- Runtime : `click` (CLI), `jinja2` (rendu du rapport), `requests` (sondes GraphQL),
  `pyyaml` (lecture des `docker-compose.yml` des livrables), `rich` (sortie console).
- Dev : `pytest`, `ruff`.
- Benchmark Blender : `numpy` (1.26.4, aligné sur le Python embarqué de Blender) et `Pillow`
  pour l'analyse d'images côté hôte, et **Blender 4.5 LTS** (hors PATH :
  `~/.local/bin/blender45`, ou `HEXA_BLENDER_BIN`), dont le Python embarqué n'a pas Pillow —
  d'où le partage « bpy mesure, l'hôte note ». `ffmpeg` (facultatif) assemble le turntable.

Les versions sont **épinglées à l'exact** (`==`), pas en plage. Un audit doit rester reproductible
dans le temps : une montée de version silencieuse d'une dépendance peut déplacer un score.

## Node — le frontend de la knowledge base

Déclaré dans `package.json` (`hexa-ai-benchmark-kb`, `"type": "module"`).

- **Node ≥ 18**, React 18, Vite 5, `@vitejs/plugin-react`.
- Aucune dépendance de rendu côté serveur : le build produit un bundle statique.

## Ce qui n'existe pas (et pourquoi c'est notable)

- **Pas de CI.** `pyproject.toml` le dit explicitement : outillage « local dev; no CI ». Les
  contrôles de qualité sont à la main du développeur, pas d'un pipeline. Voir
  [`../REGLES/process.md`](../REGLES/process.md).
- **Pas de TypeScript dans ce dépôt.** Le TypeScript est le langage des *livrables audités*, pas
  celui de l'outil. La confusion est facile : voir [contrat-livrable.md](contrat-livrable.md) pour
  ce qui relève du livrable.
