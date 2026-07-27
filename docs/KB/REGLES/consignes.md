---
titre: Consignes de l'utilisateur envers Claude
type: regle
statut: a-completer
maj: 2026-07-27
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

## À COMPLÉTER

Les autres consignes se capitaliseront au fil des sessions, via `/capitalize`.
