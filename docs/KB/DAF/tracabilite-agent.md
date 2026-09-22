---
titre: Traçabilité de l'agent — ce qui est auto-déclaré
type: daf
statut: actif
maj: 2026-09-22
---

# Traçabilité de l'agent

L'agent évalué dépose un `audit_trace.json` à la racine de son livrable (format dans
[`README.md`](../../../README.md)). Il vaut 10 % du score : présence, validité, cohérence
summary ↔ phases (±10 %), et métriques d'efficacité (turns, tool calls, wall time).

## L'invariant à ne jamais oublier

**Ce fichier est rempli par l'agent audité lui-même.** Aucun de ses champs n'est vérifié contre une
mesure externe. En particulier `meta.model`, `meta.prompt_version` et les compteurs d'effort sont
des **déclarations**, pas des observations.

Conséquences opérationnelles :

- Un run peut afficher un modèle qui n'est pas celui réellement utilisé. C'est la raison d'être du
  mécanisme d'overrides — voir [`../DAT/kb-magasin-donnees.md`](../DAT/kb-magasin-donnees.md).
- Comparer deux agents sur leurs métriques d'efficacité déclarées n'a de valeur que si l'on fait
  confiance aux deux déclarations. Le scoring de la phase 3 mesure donc surtout la **discipline**
  (l'agent a-t-il joué le jeu de la traçabilité), pas la performance réelle.

Ne pas « corriger » ce design en supprimant la phase 3 : la discipline déclarative est justement
ce qu'on veut mesurer. Mais ne jamais présenter ces chiffres comme des faits mesurés.

## Recouper avec une mesure externe

Depuis le 2026-09-22, `scripts/session_usage.py` lit le transcript de la session (Claude Code ou
Codex) et en extrait les tokens réels (cache inclus, écritures de cache 5m/1h séparées), le
modèle, l'**effort réel** et la durée, puis les confronte à l'`audit_trace.json`. C'est un outil
d'opérateur : il n'alimente pas le scoring, il sert à lever le doute avant publication.

Pourquoi c'est devenu nécessaire : le pilier Coût (12 % en v2) est calculé sur les tokens déclarés.
Un run peut gagner les 12 points avec des compteurs invraisemblables (p. ex. 33k tokens d'entrée
déclarés pour 38 appels d'outils) pendant qu'un run honnête les perd.

## À COMPLÉTER

- Faut-il faire entrer la mesure du transcript dans le score (et avec quelle règle quand il n'est
  pas disponible, p. ex. runs sur une autre machine) ?
- La bande `total_turns` 5..15 contredit le mode « session entièrement autonome » de l'énoncé : un
  agent honnête déclare 1 échange et prend 0. Réviser la bande ou la définition du champ.
