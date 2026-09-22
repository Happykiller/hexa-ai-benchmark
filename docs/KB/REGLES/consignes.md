---
titre: Consignes de l'utilisateur envers Claude
type: regle
statut: a-completer
maj: 2026-09-22
---

# Consignes

Page alimentée par `/capitalize` au fil des sessions. Une consigne née d'une **correction** de
l'utilisateur a plus de valeur que toutes les autres : elle est ici pour ne pas se reproduire.

## Langue

Le projet, ses documents, sa KB, ses commits et les échanges sont en **français** — sans exception
depuis l'unification sur Claude Code.

## Une seule source, pas de doublon d'instructions

L'utilisateur a supprimé `AGENTS.md` (multi-agents : Claude, Gemini, Codex) au profit du seul
`CLAUDE.md`. **Pourquoi** : deux fichiers d'instructions pour un même projet, c'est deux vérités
qui divergent — et `CLAUDE.md` était en plus non tracké, donc invisible pour le dépôt.

**Comment l'appliquer** : ne pas recréer de fichier d'instructions par agent tiers ; ne pas
recopier dans `CLAUDE.md` ce que la KB porte déjà. Devant un doublon documentaire, signaler et
proposer la fusion plutôt que d'entretenir les deux.

## Sessions longues : aller au bout en autonomie

Quand l'utilisateur demande une session « longue, sans interruption, jusqu'au bout », il attend
un travail mené d'une traite : trancher seul les ambiguïtés (en les signalant dans le compte
rendu), vérifier plutôt que demander, et ne poser les questions de décision (commit, publication,
doctrine) qu'**à la fin**. **Pourquoi** : demande explicite du 2026-09-22, pour une revue avant
soumission d'un run.

**Comment l'appliquer** : les décisions qui changent un score publié ou le contenu d'un livrable
restent à l'utilisateur — les instruire complètement (chiffrage de l'impact) et les lui présenter
en fin de session, sans bloquer le reste du travail.

## À COMPLÉTER

Les autres consignes se capitaliseront au fil des sessions, via `/capitalize`.
