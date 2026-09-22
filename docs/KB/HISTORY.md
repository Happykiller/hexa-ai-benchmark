---
titre: Historique des sujets abordés
type: index
statut: actif
maj: 2026-09-04
---

# Historique

Index des sessions **utiles** — pas un journal de commits, git le fait déjà. Une ligne par session
ayant produit un acquis, pour ne pas refaire deux fois le même chemin.

Au-delà de ~200 lignes, découper par année (`HISTORY/README.md` + `HISTORY/2026.md`).

| Date | Sujet | Ce qui en est sorti | Traces |
|---|---|---|---|
| 2026-07-27 | Accueil de session | Hook `SessionStart` qui scanne `.claude/` et rappelle l'outillage en tête de première réponse | [MOTEUR.md](MOTEUR.md) |
| 2026-07-27 | Mise en place du ghost | Squelette KB + amorce DAT/DAF/REGLES depuis le dépôt réel, cartographie du moteur, skill `/capitalize` | [README.md](README.md) |
| 2026-07-27 | Unification sur Claude Code | `AGENTS.md` supprimé (contenu reversé en DAT), `CLAUDE.md` devient l'entrée unique et versionnée, `.claude/` outillage versionné | [REGLES/lois.md](REGLES/lois.md), [DAT/contrat-livrable.md](DAT/contrat-livrable.md) |
| 2026-09-04 | Consigne : boy scout rule | Corriger ce qu'on croise, sans redemander — en réparant la cause et en laissant une preuve. Première application : les chemins machine dans `data.json` | [REGLES/consignes.md](REGLES/consignes.md) |
| 2026-09-04 | Installation du rituel `/cloture` | Skill de clôture créé avec un périmètre atypique : **aucune stack compose propre au projet**, les conteneurs viennent des livrables audités et survivent même à un `--skip-dynamic`. `/capitalize` trouvé conforme à la référence, non modifié | [MOTEUR.md](MOTEUR.md), [DAT/environnements.md](DAT/environnements.md) |
| 2026-09-04 | Revue de reprise après 5 semaines | Moteur sain (82 tests verts, bundle en phase avec `src/`). Trois trous trouvés : un rebuild KB complet aurait effacé 2 runs publiés sans source locale → garde-fou `KnowledgeBaseShrinkError` + `--allow-drop` ; prix Sonnet 5 périmé depuis le 2026-08-31 → $3/$15 ; README et KB décrivaient encore le scoring v1 alors que v2 (5 piliers, pilier Coût 12 %) est le défaut depuis juin | [DAT/kb-magasin-donnees.md](DAT/kb-magasin-donnees.md), [DAF/piliers-notation.md](DAF/piliers-notation.md), [REGLES/lois.md](REGLES/lois.md) |
| 2026-09-22 | Revue avant soumission d'Opus 5.5 | Tarifs Opus 5.5 / Fable 5.1, Sonnet 5 remis à $2/$10 (la hausse n'a pas eu lieu), parsing Jest (`Tests:`), cap « stack non démarrée », contrôles positifs E2E, faux négatifs statiques (guard, teardown, healthcheck, fichiers vides), data.js (KB ouvrable en file://), `scripts/session_usage.py` | [DAT/auditeur-pipeline.md](DAT/auditeur-pipeline.md), [DAF/tracabilite-agent.md](DAF/tracabilite-agent.md) |
| 2026-09-22 | Capitalisation de la revue | Loi n°10 (pas d’audit pendant un run), workflow d'audit complété (étape 0, recoupement des tokens, ré-audit des comparables), lieu des runs, consigne « sessions longues » | [REGLES/lois.md](REGLES/lois.md), [REGLES/workflows.md](REGLES/workflows.md) |
