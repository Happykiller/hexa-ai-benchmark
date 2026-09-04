---
titre: Consignes de l'utilisateur envers Claude
type: regle
statut: actif
maj: 2026-09-04
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

## Boy scout rule — on corrige ce qu'on trouve, au fur et à mesure

Consigne donnée le 2026-09-04, mot pour mot : *« on corrige ce qu'on trouve au fur à mesure c'est
la boy scout rule »*.

**Pourquoi** : sur un projet consulté par à-coups (cinq semaines entre deux sessions), un défaut
signalé mais non corrigé n'est pas « noté pour plus tard », il est perdu. Le coût de le re-trouver
dépasse celui de le corriger sur-le-champ, tant qu'on est dans le contexte.

**Comment l'appliquer** :

- Un défaut croisé en chemin se corrige dans la foulée, **sans redemander la permission** — ne pas
  se contenter de le signaler en fin de rapport.
- Corriger la **cause**, pas le symptôme. Des chemins machine dans un fichier versionné ne se
  nettoient pas à la main : on répare le code qui les produit, puis on migre les données.
- Rester **vérifiable** : chaque correction opportuniste s'accompagne de sa preuve (un test, un
  diff borné, un contrôle rejoué), pour qu'elle ne devienne pas une régression cachée dans un
  gros lot.
- La limite reste les **lois** : une correction ne justifie jamais de hand-editer une source brute
  ni de faire disparaître une entrée publiée. Devant ce cas, on s'arrête et on expose.
