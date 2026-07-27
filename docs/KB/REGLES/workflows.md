---
titre: Workflows outillés
type: regle
statut: actif
maj: 2026-07-27
---

# Workflows

## Auditer un livrable, de bout en bout

L'ordre compte : chaque étape suppose la précédente réussie.

1. **Vérifier la propriété du livrable** (piège `faro` — voir
   [`../DAT/environnements.md`](../DAT/environnements.md)). Avant, pas après.
2. **Vérifier les prérequis Docker** et la disponibilité du port 4000.
3. **Lancer l'audit** (`analyze livrables/<...>`) — long, à traiter comme une tâche de fond.
   Le sous-agent [`audit-runner`](../MOTEUR.md) existe pour ça.
4. **Lire le score par phase** avant de conclure : un total à 40 % appelle une vérification du cap
   (build réellement cassé, ou artefact d'environnement ?).
5. **Intégrer à la KB** : upsert de l'entrée depuis le `cr_audits/*.json` produit.
6. **Corriger les métadonnées si besoin** via `overrides.json`, puis rejouer le build.
7. **Committer** `knowledge_base/` avec un message `kb(...)` portant modèle et score.

Le rebuild du bundle web n'est nécessaire **que** si `src/` a changé.

## Faire évoluer l'auditeur

- Ajouter un contrôle statique → **une entrée dans le registre** de `auditor/challenges.py`, sans
  toucher `main.py`.
- Itérer sur les checkers → toujours `--skip-dynamic`, sinon chaque essai coûte plusieurs minutes
  de Docker.
- Toucher au template `report.md` → vérifier `kb/markdown_parser.py`, qui en dépend.

## Capitaliser

En fin de session utile : `/capitalize`. Voir [`../MOTEUR.md`](../MOTEUR.md).
