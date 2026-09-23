---
titre: Arborescence — rôle des dossiers de premier niveau
type: dat
statut: actif
maj: 2026-09-23
---

# Arborescence

Trois familles de dossiers cohabitent : **l'outil**, **les données**, **le rendu**. Les confondre
est la première source d'erreur sur ce dépôt.

## Le principe

Depuis le 2026-09-23 : **un dossier par benchmark, un noyau commun, les données rangées par
nature**. Le code est un paquet Python (`hexa`) avec une CLI unique (`python3 -m hexa`).
Tous les chemins sont définis dans `hexa/paths.py`, aucun n'est codé ailleurs.

## Le code

| Dossier | Rôle |
|---|---|
| `hexa/core/engine/` | Notation commune : indicateurs, piliers, caps, traçabilité, coût, barème commun (`config.py`). Ne connaît aucun benchmark : le barème des piliers est passé par l'appelant |
| `hexa/core/kb/` | Magasin KB générique (`store.py` : upsert, garde-fou anti-perte, data.js), briques de normalisation (`common.py`) et cartes communes (`cards.py`) |
| `hexa/core/tools/` | `session_usage.py` (`python3 -m hexa usage`) |
| `hexa/benches/todo/` | Benchmark Todo List : `auditor/` (ex-`auditor/`), `enonce/`, `kb/`, `tests/`, `http/` (requêtes manuelles) |
| `hexa/benches/blender/` | Benchmark Blender : `auditor/`, `bpy/` (scripts exécutés dans Blender), `challenges/`, `kb/`, `tests/` |
| `web/` | Front React/Vite unique ; `HEXA_SITE=todo\|blender` choisit le site construit |

## Les données

| Dossier | Rôle | Versionné ? |
|---|---|---|
| `runs/<bench>/livrables/` | Dossiers soumis par les agents — l'entrée de l'audit | **Non** |
| `runs/<bench>/cr_audits/` | Rapports d'audit `.json` + `.md` (+ `_media/` pour Blender) — la source brute immuable | **Non** |
| `sites/<bench>/` | KB publiée : `data.json`, `data.js`, `overrides.json`, bundle web, médias | Oui |

`runs/` n'étant pas versionné, chaque machine migre ses données une fois après l'arrivée de cette
arborescence : `python3 -m hexa migrate-layout` (voir `--dry-run`).

## Divers

- `hexa/benches/todo/http/test.http` — requêtes GraphQL manuelles pour sonder un livrable démarré.
- `.vscode/settings.json` — réglage d'éditeur (port Live Server), sans effet sur le projet.
- `CLAUDE.md` — **le** point d'entrée des instructions agent, versionné. Il a remplacé `AGENTS.md`
  (unification sur Claude Code, 2026-07-27) : voir [`../REGLES/lois.md`](../REGLES/lois.md).
- `docs/KB/` — cette base de connaissance, versionnée.
- `.claude/` — outillage agent versionné (`skills/`, `agents/`, `hooks/`), sauf
  `settings.local.json` qui reste local : voir [`../REGLES/lois.md`](../REGLES/lois.md).
