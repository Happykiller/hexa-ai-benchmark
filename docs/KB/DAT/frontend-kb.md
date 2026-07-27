---
titre: Frontend de consultation de la KB
type: dat
statut: actif
maj: 2026-07-27
---

# Frontend de la knowledge base

Application React 18 minimale (`src/App.jsx`, `src/main.jsx`, `src/styles.css`) buildée par Vite
vers `knowledge_base/`.

## Le point à connaître : data et bundle sont découplés

`data.json` est **chargé au runtime**, pas inliné au build. Donc :

- ajouter un audit → régénérer `data.json` suffit, le bundle web n'a pas à être reconstruit ;
- modifier `src/` → il faut `npm run build:kb:web`.

C'est ce qui rend l'ajout d'un run peu coûteux, et c'est pourquoi les scripts npm distinguent
`build:kb:data`, `build:kb:web` et `build:kb` (les deux).

## Sortie versionnée

`knowledge_base/` est **dans** le dépôt, contrairement à `cr_audits/` et `livrables/`. Le bundle
généré (`index.html`, `assets/`) est donc committé : c'est un artefact de build versionné,
assumé, parce qu'il tient lieu de publication.

## À COMPLÉTER

- Où la KB est-elle publiée / consultée (hébergement, URL) ? Ou reste-t-elle locale ?
- Y a-t-il des conventions d'affichage à préserver dans `App.jsx` (tri, filtres attendus) ?
