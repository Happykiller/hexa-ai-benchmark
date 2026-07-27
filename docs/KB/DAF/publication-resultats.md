---
titre: Publication et usage des résultats
type: daf
statut: a-completer
maj: 2026-07-27
---

# Publication et usage des résultats

## Ce qui est constatable dans le dépôt

Un audit produit trois sorties : un rapport lisible `.md`, les données brutes `.json` (les deux
dans `cr_audits/`, non versionné) et une copie du rapport dans le dossier du livrable. La
publication passe ensuite par `knowledge_base/data.json` + le rendu web, qui, eux, sont versionnés.

Le coût estimé d'un run ($, tokens, points par dollar) est calculé et affiché dans le détail d'une
entrée — le benchmark ne mesure donc pas que la qualité, mais aussi le **rapport qualité/prix**.

À ce jour, 18 livrables et 17 audits sont présents localement, couvrant des modèles Claude, GPT et
Gemini à différents niveaux d'effort.

## À COMPLÉTER — questions ouvertes

- **À qui s'adresse la KB publiée** : usage personnel, équipe, publication externe ?
- **Quelle politique de comparabilité** : compare-t-on des runs de `prompt_version` différentes
  dans un même classement, ou les sépare-t-on ?
- **Que fait-on d'un run raté pour cause d'environnement** : on le republie corrigé, on le
  supprime, on le garde avec une mention ?
- **Sur quel critère décide-t-on d'auditer un nouveau modèle** (sortie d'un modèle, demande, veille) ?
- La source du coût unitaire ($/token par modèle) est-elle maintenue à la main quelque part ?
