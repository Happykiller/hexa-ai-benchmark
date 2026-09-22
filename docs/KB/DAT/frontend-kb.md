---
titre: Frontend de consultation de la KB
type: dat
statut: actif
maj: 2026-09-22
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

## Ouvrable par double-clic (`file://`)

En `file://`, Chrome bloque les scripts `type="module"`, tout attribut `crossorigin` et tout
`fetch` (origine `null`) : la page restait **blanche** (constaté le 2026-09-22). D'où trois choix :

- le builder écrit `knowledge_base/data.js` (`window.__HEXA_KB__ = {entries, prompt}`) à chaque
  écriture de `data.json` — les deux ne doivent jamais diverger ;
- `index.html` charge `data.js` puis le bundle en scripts classiques (`defer`) : Vite émet un
  bundle **IIFE**, CSS incluse, et un plugin de `vite.config.js` retire `type="module"` /
  `crossorigin` ;
- le front lit `window.__HEXA_KB__` s'il existe, sinon retombe sur le `fetch` (mode dev,
  serveur HTTP).

Vérifier un changement du front : Chrome headless Windows
(`chrome.exe --headless=new --dump-dom` ou `--screenshot`) sur l'URL `file:///…` **et** en HTTP.

## Sortie versionnée

`knowledge_base/` est **dans** le dépôt, contrairement à `cr_audits/` et `livrables/`. Le bundle
généré (`index.html`, `assets/`) est donc committé : c'est un artefact de build versionné,
assumé, parce qu'il tient lieu de publication.

## À COMPLÉTER

- Où la KB est-elle publiée ? Aucun hébergement trouvé au 2026-09-22 (pas de GitHub Pages, rien
  dans le dépôt) : consultation locale, par double-clic ou `npm run dev`.
- Y a-t-il des conventions d'affichage à préserver dans `App.jsx` (tri, filtres attendus) ?
