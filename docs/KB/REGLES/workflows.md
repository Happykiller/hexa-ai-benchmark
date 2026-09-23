---
titre: Workflows outillés
type: regle
statut: actif
maj: 2026-09-22
---

# Workflows

## Auditer un livrable, de bout en bout

L'ordre compte : chaque étape suppose la précédente réussie.

0. **Attendre la fin de la session de l'agent**, puis `make down` dans son dossier de travail
   avant de déplacer le livrable dans `runs/todo/livrables/`. Sa stack occupe 4000 / 47017 / 43306 sous un
   nom de projet compose fixe : l'auditeur sonderait son API, et son `docker compose down -v`
   détruirait la stack de l'agent (loi n°10).
1. **Vérifier la propriété du livrable** (piège `faro` — voir
   [`../DAT/environnements.md`](../DAT/environnements.md)). Avant, pas après.
2. **Vérifier les prérequis Docker** et la disponibilité du port 4000.
3. **Lancer l'audit** (`analyze runs/todo/livrables/<...>`) — long, à traiter comme une tâche de fond.
   Le sous-agent [`audit-runner`](../MOTEUR.md) existe pour ça.
4. **Lire le score par phase** avant de conclure : un total à 40 % appelle une vérification du cap
   (build réellement cassé, ou artefact d'environnement ?).
5. **Recouper les métriques déclarées** : `hexa/core/tools/session_usage.py <transcript> --trace
   <livrable>/audit_trace.json`. Les tokens pilotent le pilier Coût ; un écart qui fait changer de
   bande se signale avant publication (le 2026-09-22, Opus 5.5 avait sous-estimé ses tokens de
   20-30 %, avec un changement de bande à la clé).
6. **Intégrer à la KB** : `build_kb.py --add` depuis le `runs/todo/cr_audits/*.json` produit — jamais de
   rebuild complet (voir [`../DAT/kb-magasin-donnees.md`](../DAT/kb-magasin-donnees.md)).
7. **Corriger les métadonnées si besoin** via `overrides.json`, puis rejouer le build.
8. **Committer** `sites/todo/` avec un message `kb(...)` portant modèle et score.

Le rebuild du bundle web n'est nécessaire **que** si `web/src/` a changé.

## Faire évoluer l'auditeur

- Ajouter un contrôle statique → **une entrée dans le registre** de `hexa/benches/todo/auditor/challenges.py`, sans
  toucher `main.py`.
- Itérer sur les checkers → toujours `--skip-dynamic`, sinon chaque essai coûte plusieurs minutes
  de Docker.
- Toucher au template `report.md` → vérifier `hexa/core/kb/markdown_parser.py`, qui en dépend.
- **Un tarif (`MODEL_PRICING`) se vérifie sur la page officielle, jamais sur une échéance écrite
  dans le code.** Le 2026-09-04, Sonnet 5 a été passé à $3/$15 parce que le commentaire annonçait
  la fin du prix d'introduction ; la page officielle disait au contraire que la hausse n'aurait
  pas lieu, et il a fallu revenir à $2/$10 le 2026-09-22. Une date dans un commentaire est une
  alerte de revérification, pas une source.
- Un nouveau motif de checker (regex statique) se **valide contre les livrables présents** dans
  `runs/todo/livrables/` avant d'être adopté : c'est ce qui a prouvé les faux négatifs du 2026-09-22 (guard
  d'auth, teardown, healthcheck), là où un test synthétique seul aurait confirmé le biais.
- **Une correction qui change un score oblige à ré-auditer les runs comparables** avant de publier
  le nouveau. Pourquoi : à livrable identique, Opus 5 passait de 75,78 % à ~82 % après les
  correctifs du 2026-09-22 — publier le nouveau run seul, noté par l'auditeur corrigé, aurait
  faussé la comparaison. Les runs dont le livrable n'est pas sur la machine restent notés à
  l'ancienne : le dire dans la publication.

## Capitaliser

En fin de session utile : `/capitalize`. Voir [`../MOTEUR.md`](../MOTEUR.md).
