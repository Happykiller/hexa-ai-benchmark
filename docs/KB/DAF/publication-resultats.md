---
titre: Publication et usage des résultats
type: daf
statut: a-completer
maj: 2026-09-04
---

# Publication et usage des résultats

## Ce qui est constatable dans le dépôt

Un audit produit trois sorties : un rapport lisible `.md`, les données brutes `.json` (les deux
dans `cr_audits/`, non versionné) et une copie du rapport dans le dossier du livrable. La
publication passe ensuite par `knowledge_base/data.json` + le rendu web, qui, eux, sont versionnés.

Le coût estimé d'un run ($, tokens, points par dollar) est affiché dans le détail d'une entrée —
mais ce n'est **pas qu'un affichage** : depuis le scoring v2, le coût est un **pilier noté à 12 %**.
Le benchmark ne mesure donc pas que la qualité, il note le **rapport qualité/prix**.

Ce que ça implique pour la lecture d'un classement : un modèle cher est structurellement pénalisé,
même livrable égal. Les bandes de coût sont absolues (en $ de session), pas relatives aux autres
runs — un modèle premium peut donc perdre les 12 % en totalité pendant qu'un modèle frugal les
prend en entier.

À ce jour, 19 entrées sont publiées dans la KB pour 18 livrables et 17 audits présents localement
(deux runs publiés n'ont plus leur source brute sur cette machine — voir
[`../DAT/kb-magasin-donnees.md`](../DAT/kb-magasin-donnees.md)), couvrant des modèles Claude, GPT
et Gemini à différents niveaux d'effort.

## Décidé

- **La source du coût unitaire** est `MODEL_PRICING` dans `auditor/scoring_config.py`, maintenue
  **à la main**, avec sa date de vérification dans `PRICING_UPDATED`. C'est une dette d'entretien
  assumée : un prix fournisseur qui change sans être répercuté fausse les runs suivants.

## À COMPLÉTER — questions ouvertes

- **À qui s'adresse la KB publiée** : usage personnel, équipe, publication externe ?
- **Quelle politique de comparabilité** : compare-t-on des runs de `prompt_version` différentes
  dans un même classement, ou les sépare-t-on ? Même question, plus aiguë, pour les runs v1 vs v2 —
  le classement actuel les mélange sans le signaler (loi n°9).
- **Que fait-on d'un run raté pour cause d'environnement** : on le republie corrigé, on le
  supprime, on le garde avec une mention ?
- **Sur quel critère décide-t-on d'auditer un nouveau modèle** (sortie d'un modèle, demande, veille) ?
- **À quelle fréquence revoit-on `MODEL_PRICING`** — et faut-il un contrôle qui alerte quand
  `PRICING_UPDATED` dépasse N mois ?
