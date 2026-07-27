---
titre: Cerveau moteur — cartographie de .claude/
type: dat
statut: actif
maj: 2026-07-27
---

# Cerveau moteur

Ce que Claude sait **faire** sur ce projet. À distinguer de la KB, qui est ce qu'il doit **savoir**.

Cet outillage est **versionné** (`skills/`, `agents/`, `hooks/`) : le modifier est un changement de
projet, à committer et à refléter ici. Seul `.claude/settings.local.json` reste hors dépôt — voir
[`REGLES/lois.md`](REGLES/lois.md).

## Skills

| Skill | Quand l'utiliser | Fichier |
|---|---|---|
| `capitalize` | En fin de session ayant produit un apprentissage : décide ce qui rejoint la KB et ce qui mérite un outil. À ne pas lancer sur une session sans acquis — la KB ne doit grossir que de ce qui sert | `.claude/skills/capitalize/SKILL.md` |

## Sous-agents

| Agent | Pourquoi il est isolé du contexte principal | Fichier |
|---|---|---|
| `audit-runner` | Un audit complet est long et très bavard (sortie Docker, make, E2E). L'isoler évite de noyer le contexte principal sous des logs dont seul le récap final compte. Il porte aussi les gestes de préparation faciles à oublier (droits `faro`, prérequis Docker) | `.claude/agents/audit-runner.md` |
| `kb-builder` | Le rebuild de la KB est mécanique et vérifiable seul : on veut le résultat (entrées régénérées, rebuild web nécessaire ou non), pas le déroulé | `.claude/agents/kb-builder.md` |

Les deux correspondent aux deux moitiés du workflow d'audit décrit dans
[`REGLES/workflows.md`](REGLES/workflows.md) : produire le rapport, puis le publier.

## Hooks

| Événement | Ce qu'il automatise | Fichier |
|---|---|---|
| `SessionStart` (`startup`) | Scanne `.claude/` au démarrage et injecte un rappel des skills, sous-agents, MCP et commandes disponibles, affiché en tête de la première réponse | `.claude/hooks/welcome.py` |

**Complémentarité avec cette page** : `welcome.py` dit *ce qui est disponible maintenant* (il
rescanne à chaque démarrage, donc il ne se périme jamais). `MOTEUR.md` dit *pourquoi ça existe et
quand s'en servir* — ce qu'aucun scan automatique ne peut produire. Les deux sont en place ; ne pas
chercher à en supprimer un au profit de l'autre.

## MCP

Aucun serveur MCP déclaré au niveau du projet (pas de `.mcp.json`). Des serveurs peuvent être
disponibles au niveau utilisateur, hors périmètre de ce dépôt.

## Settings

`.claude/settings.local.json` porte les permissions locales et le branchement du hook d'accueil.
Une seule entrée `SessionStart` : un accueil affiché deux fois est un bug.
