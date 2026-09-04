---
titre: Arborescence — rôle des dossiers de premier niveau
type: dat
statut: actif
maj: 2026-09-04
---

# Arborescence

Trois familles de dossiers cohabitent : **l'outil**, **les données**, **le rendu**. Les confondre
est la première source d'erreur sur ce dépôt.

## L'outil

| Dossier | Rôle |
|---|---|
| `auditor/` | Moteur d'audit Python. CLI (`main.py`), scoring, profil de défi, `modules/`, `templates/report.md`, `tests/` |
| `kb/` | Package Python de construction du magasin de données KB (normalisation, parsing markdown, rendu des sections) |
| `scripts/` | Points d'entrée CLI fins (`build_kb.py` n'est qu'un wrapper de `kb/builder.py`) |
| `src/` | Application React de consultation de la KB (`App.jsx`, `main.jsx`, `styles.css`) |

## Les données

| Dossier | Rôle | Versionné ? |
|---|---|---|
| `livrables/` | Dossiers soumis par les agents évalués — l'entrée de l'audit | **Non** (`.gitignore`) |
| `cr_audits/` | Rapports d'audit `.json` + `.md` — la source brute immuable | **Non** (`.gitignore`) |
| `knowledge_base/` | Sortie publiée : `data.json`, `overrides.json`, bundle web | Oui |
| `prompts/` | `evaluation_prompt.md` — l'énoncé remis aux agents | Oui |

Le fait que `livrables/` et `cr_audits/` soient hors dépôt est structurant : **les données brutes
d'audit ne survivent que sur la machine qui a lancé l'audit**. Ce qui est partagé, c'est le dérivé
(`knowledge_base/data.json`). D'où l'importance de la chaîne décrite dans
[kb-magasin-donnees.md](kb-magasin-donnees.md), et du garde-fou qui empêche un rebuild d'effacer
une entrée dont le brut a disparu.

Le builder scanne **deux** emplacements de rapports (`kb/constants.py:SCAN_DIRS`) : `cr_audits/` à
la racine et `auditor/cr_audits/`, un vestige des premiers runs lancés depuis `auditor/`. Le second
est vide aujourd'hui mais reste lu — un `cr_*.json` qui y traîne remonterait dans la KB.

## Divers

- `http/test.http` — requêtes GraphQL manuelles pour sonder un livrable démarré.
- `index.html`, `vite.config.js` — racine du build Vite, qui écrit dans `knowledge_base/`.
- `CLAUDE.md` — **le** point d'entrée des instructions agent, versionné. Il a remplacé `AGENTS.md`
  (unification sur Claude Code, 2026-07-27) : voir [`../REGLES/lois.md`](../REGLES/lois.md).
- `docs/KB/` — cette base de connaissance, versionnée.
- `.claude/` — outillage agent versionné (`skills/`, `agents/`, `hooks/`), sauf
  `settings.local.json` qui reste local : voir [`../REGLES/lois.md`](../REGLES/lois.md).
