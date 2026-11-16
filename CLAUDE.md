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
| Lancer un audit, rebuild la KB | [`README.md`](README.md) — `python3 -m hexa --help` |
| Où est quoi (un dossier par benchmark) | [`docs/KB/DAT/arborescence.md`](docs/KB/DAT/arborescence.md) |
| Comprendre le pipeline d'audit | [`docs/KB/DAT/auditeur-pipeline.md`](docs/KB/DAT/auditeur-pipeline.md) |
| Ce qu'un livrable doit fournir | [`docs/KB/DAT/contrat-livrable.md`](docs/KB/DAT/contrat-livrable.md) |
| Pièges d'exécution (droits, bind-mounts) | [`docs/KB/DAT/environnements.md`](docs/KB/DAT/environnements.md) |
| Benchmark Blender 3D (second défi) | [`docs/KB/DAT/blender-pipeline.md`](docs/KB/DAT/blender-pipeline.md) |
| Ne rien casser | [`docs/KB/REGLES/lois.md`](docs/KB/REGLES/lois.md) |

Le projet et ses documents sont en **français**.

En fin de session de travail, lance `/cloture` : il capitalise, committe et pousse tous les
dépôts du projet, puis arrête les conteneurs. Pour capitaliser seul, sans refermer la session :
`/capitalize`.

## Distro KoA

Ce dépôt est aussi une **seed KoA** (`koa.profil`, `bootstrap.sh`) : KoA en fait une distro WSL
dédiée, cluster `perso`, où tu démarres dans `~/hexa-ai-benchmark`. Le `bootstrap.sh` y installe
Blender 4.5 LTS (`~/.local/bin/blender45`, hors PATH), le venv `venv/` et les dépendances web ;
le socle KoA fournit Python, Node et Docker sans root.

**À ta première consigne**, vérifie l'environnement puis rends compte en quelques lignes :
`~/bootstrap.log` se termine par `terminé` ; `venv/bin/python -m hexa --help` répond ;
`~/.local/bin/blender45 --version` donne 4.5 ; `docker info` et `docker compose version`
répondent ; `ssh -T git@github.com` reconnaît la deploy key. Les dossiers `runs/*/livrables/`
sont vides dans une distro neuve (gitignorés) : un livrable à auditer arrive par l'opérateur.

**Périmètre** : ce seul dépôt, `Happykiller/hexa-ai-benchmark`. N'explore ni ne cite aucun autre
projet que tes accès t'ouvriraient. Tu n'écris jamais toi-même de règle de permission : demande-la
par `permission_demander`. Sous Docker sans root, les limites `--memory` / `--cpus` ne s'appliquent
pas.

Attention aux conteneurs : ils ne viennent pas du projet mais du **livrable audité**, et un audit
même `--skip-dynamic` peut en laisser tourner. Un working tree propre ne prouve rien à ce sujet —
`runs/` (livrables et rapports bruts) est gitignoré.
