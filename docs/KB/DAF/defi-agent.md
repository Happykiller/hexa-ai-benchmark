---
titre: Le défi imposé aux agents
type: daf
statut: actif
maj: 2026-09-22
---

# Le défi imposé aux agents

L'énoncé remis aux agents est `hexa/benches/todo/enonce/evaluation_prompt.md` (copié dans `sites/todo/` pour
consultation). Il demande une **Todo List multi-bases** en TypeScript / GraphQL, en architecture
hexagonale, avec double persistance MongoDB (tâches) + MySQL (utilisateurs), auth JWT, injection de
dépendances InversifyJS, et Docker Compose opérationnel.

## Pourquoi ce sujet-là

Chaque contrainte du sujet est là pour rendre une compétence **mesurable** :

| Contrainte | Ce qu'elle révèle |
|---|---|
| Architecture hexagonale | L'agent sait-il tenir une isolation de couches sous pression, ou l'abandonne-t-il dès que ça coûte ? |
| Double persistance (Mongo + MySQL) | Sait-il faire coexister deux modèles de données sans les fusionner par facilité ? |
| Auth JWT | Produit-il de la sécurité réelle ou une façade qui « passe le happy path » ? |
| Docker Compose + `make start` | Le livrable démarre-t-il vraiment chez quelqu'un d'autre ? |
| Graphe de dépendances entre tâches | Sait-il implémenter une **vraie** règle métier, pas un CRUD |

La règle métier des dépendances (une tâche bloquée tant que ses pré-requis ne sont pas terminés)
est le cœur fonctionnel : c'est la seule partie du sujet qu'aucun scaffolding ne fournit.

## Version du prompt

L'énoncé est versionné (`prompt_version`) et cette version est attendue dans l'`audit_trace.json`.
Deux runs de prompts différents ne sont **pas comparables** : c'est ce champ qui permet de le savoir.

La version courante est **`2606082200`**, déclarée à deux endroits qui doivent rester alignés :
l'en-tête de `hexa/benches/todo/enonce/evaluation_prompt.md` et `prompt_version` dans le `ChallengeProfile`
(`hexa/benches/todo/auditor/challenges.py`). Ne pas recopier ce numéro ailleurs dans la KB — il se périme.

## Où tournent les runs

Les agents produisent leur livrable dans `/home/admin/test/<AAAAMMJJ_HHMM_modèle_temp>/`, pas
dans `runs/todo/livrables/` : l'opérateur l'y dépose une fois la session terminée. Pour un run Claude Code,
le transcript est dans `~/.claude/projects/-home-admin-test/<session>.jsonl` — c'est la source de
la mesure réelle (tokens, effort, durée) via `hexa/core/tools/session_usage.py`. Le suffixe du nom de
dossier est la **température**, pas l'effort.

## À COMPLÉTER

- Le défi est-il destiné à évoluer (nouveaux sujets), ou reste-t-il figé pour préserver la
  comparabilité historique des runs ?
