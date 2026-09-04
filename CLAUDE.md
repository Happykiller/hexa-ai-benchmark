# hexa-ai-benchmark — instructions projet

Framework d'évaluation de la capacité des agents IA à livrer une application **opérationnelle** :
un auditeur Python note un livrable soumis par un agent (Todo List hexagonale multi-bases,
TypeScript/GraphQL) sur cinq piliers, et publie le résultat dans une knowledge base web.

Ce fichier est le **point d'entrée unique** des instructions agent de ce dépôt. Il n'y a plus de
`AGENTS.md` / `CODEX.md` / `GEMINI.md` : le projet est unifié sur Claude Code.

## Base de connaissance

La mémoire longue du projet est dans [`docs/KB/`](docs/KB/README.md) :
architecture technique ([`DAT/`](docs/KB/DAT/README.md)), architecture fonctionnelle
([`DAF/`](docs/KB/DAF/README.md)), règles du projet ([`REGLES/`](docs/KB/REGLES/README.md)),
outillage ([`MOTEUR.md`](docs/KB/MOTEUR.md)) et historique des sujets
([`HISTORY.md`](docs/KB/HISTORY.md)).

**Avant d'agir sur un sujet, consulte l'index concerné.** Les pages `REGLES/lois.md` et
`REGLES/consignes.md` sont contraignantes : elles priment sur tes défauts.

## Repères immédiats

| Besoin | Où aller |
|---|---|
| Lancer un audit, rebuild la KB | [`README.md`](README.md) — commandes exactes |
| Comprendre le pipeline d'audit | [`docs/KB/DAT/auditeur-pipeline.md`](docs/KB/DAT/auditeur-pipeline.md) |
| Ce qu'un livrable doit fournir | [`docs/KB/DAT/contrat-livrable.md`](docs/KB/DAT/contrat-livrable.md) |
| Pièges d'exécution (droits, bind-mounts) | [`docs/KB/DAT/environnements.md`](docs/KB/DAT/environnements.md) |
| Ne rien casser | [`docs/KB/REGLES/lois.md`](docs/KB/REGLES/lois.md) |

Le projet et ses documents sont en **français**.

À la fin d'une session ayant produit un apprentissage, lance `/capitalize`.
