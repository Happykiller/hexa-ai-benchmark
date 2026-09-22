---
titre: Process de livraison
type: regle
statut: actif
maj: 2026-09-22
---

# Process de livraison

## Branches

Le dépôt travaille sur **`develop`** (seule branche locale, suivie par `origin/develop`). `main`
est la branche principale déclarée. Les évolutions d'outillage passent par une branche dédiée (`fix/…`, `feat/…`) quand l'utilisateur
le demande — première occurrence : `fix/revue-avant-opus-5-5` (2026-09-22). Les ajouts de run
(`kb(...)`) restent sur `develop`.

## Messages de commit

Convention constatée dans l'historique : **Conventional Commits, sujet en français**.

```
type(scope): description à l'infinitif ou au présent
```

Types utilisés : `feat`, `fix`, `docs`, `chore`, et le type **maison `kb`** pour l'ajout d'un run
à la knowledge base. Scopes observés : `hexa`, `auditor`, `kb`, `hexa-kb`, `audit`.

Pour un ajout de run, la description porte le modèle et le score, ce qui rend l'historique lisible
comme un journal de benchmark :
`kb(hexa): ajoute le run claude-opus-5 high (75.78%)`

L'historique contient aussi des commits `up` / `update` sans contenu descriptif. Ce sont des
accidents, pas la convention — ne pas s'en inspirer.

## Revue

Pas de CI, pas de PR dans l'historique local : la revue est humaine et directe.

## À COMPLÉTER

- Existe-t-il un remote autre que `origin`, et une politique de merge `develop` → `main` ?
- Un run ajouté à la KB doit-il être committé seul, ou groupé avec d'autres ?
