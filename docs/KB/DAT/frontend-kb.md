---
titre: Frontend de consultation de la KB
type: dat
statut: actif
maj: 2026-09-23
---

# Frontend de la knowledge base

Application React 18 minimale (`src/App.jsx`, `src/main.jsx`, `src/styles.css`) buildée par Vite
vers `knowledge_base/`.

## Le point à connaître : data et bundle sont découplés

`data.json` est **chargé au runtime**, pas inliné au build. Donc :

- ajouter un audit → régénérer `data.json` suffit, le bundle web n'a pas à être reconstruit ;
- modifier `src/` → il faut `npm run build:kb:web`.

C'est ce qui rend l'ajout d'un run peu coûteux, et c'est pourquoi les scripts npm distinguent
`build:kb:data`, `build:kb:web` et `build:kb` (les deux). `dev:kb` régénère les données puis lance
le serveur de dev — le raccourci pour itérer sur l'affichage d'un run qui vient de tomber.

## Ce que le front affiche, et ce qu'il n'affiche pas

Le détail d'une entrée expose le modèle de scoring (`Modèle scoring : fib_v1|fib_v2`), le cap
éventuel (chip « Cap appliqué »), le coût et les corrections manuelles. Le **classement**, lui, ne
montre que le score : deux runs notés sur des barèmes différents (v1 / v2) y apparaissent côte à
côte sans distinction. C'est une limite connue — voir la loi n°9 dans
[`../REGLES/lois.md`](../REGLES/lois.md).

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

## Deux sites, un seul code

`src/` sert les deux KB. `vite.blender.config.js` fixe `VITE_KB_VARIANT=blender` et sort dans
`knowledge_base_blender/` (`npm run build:kb:blender:web`). Les piliers affichés viennent de
l'entrée (`bucket_scores[k].short`), avec repli sur la table Todo pour les entrées publiées avant ;
un bandeau de visuels s'affiche quand l'entrée a des `media`. Une ancre `#<id>` dans l'URL ouvre
ce run (lien partageable, et moyen de vérifier une ligne dépliée en Chrome headless).

Chrome côté Windows ne peut pas écrire sa capture dans un `/tmp` WSL : copier le site dans
`%TEMP%` Windows et y écrire le `--screenshot`.

## Sortie versionnée

`knowledge_base/` est **dans** le dépôt, contrairement à `cr_audits/` et `livrables/`. Le bundle
généré (`index.html`, `assets/`) est donc committé : c'est un artefact de build versionné,
assumé, parce qu'il tient lieu de publication.

## À COMPLÉTER

- Où la KB est-elle publiée ? Aucun hébergement trouvé au 2026-09-22 (pas de GitHub Pages, rien
  dans le dépôt) : consultation locale, par double-clic ou `npm run dev`.
- Y a-t-il des conventions d'affichage à préserver dans `App.jsx` (tri, filtres attendus) ?
