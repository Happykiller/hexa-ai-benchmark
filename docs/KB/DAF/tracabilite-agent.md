---
titre: Traçabilité de l'agent — ce qui est auto-déclaré
type: daf
statut: actif
maj: 2026-07-27
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

## À COMPLÉTER

- Existe-t-il une intention de mesurer côté auditeur (wall time réel du run) pour recouper la
  déclaration ?
