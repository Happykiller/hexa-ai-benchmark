---
titre: Environnements — installer, lancer, tester
type: dat
statut: actif
maj: 2026-07-27
---

# Environnements

Les commandes de référence sont dans [`README.md`](../../../README.md) (section « Lancer un
audit »). Cette page ne les recopie pas : elle documente ce qui **n'y est pas** — les conditions de
succès réelles.

## Prérequis d'un audit complet

- Un **venv Python** activé avec `auditor/requirements.txt` installé.
- **Docker + Docker Compose** fonctionnels : l'audit dynamique démarre la stack du livrable
  (API + MongoDB + MySQL) et sonde `http://localhost:4000/graphql`.
- Le **port 4000 libre** : l'endpoint est en dur dans le profil de défi, pas configurable.
- `--skip-dynamic` retire la totalité de ces prérequis (analyse statique seule) — c'est le mode à
  utiliser pour itérer sur les checkers sans payer 10 minutes de Docker.

## Piège n°1 — propriété des livrables

Certains livrables arrivent possédés par un autre utilisateur (`faro`). L'auditeur écrit dans le
dossier du livrable (copie du rapport) : sans droits, **le run avorte en cours de route**, après
avoir déjà consommé le temps de build. Vérifier la propriété et corriger *avant* de lancer, pas
après l'échec.

## Piège n°2 — bind-mounts créés par le daemon Docker

Si un `docker-compose.yml` de livrable monte un dossier hôte inexistant (typiquement `./coverage`),
le daemon le crée en `root:root`, ce qui casse ensuite le contexte de build
(`error from sender: … permission denied`) et produit un **faux `make build failed`** — donc le cap
à 40 %. L'auditeur pré-crée ces dossiers pour cette raison (`precreate_bind_mount_dirs`).
Un score plafonné à 40 % doit toujours faire suspecter ce mécanisme avant de conclure que le
livrable est mauvais.

## Tests de l'auditeur

`pyproject.toml` déclare `testpaths = ["auditor/tests"]` et un `pythonpath = ["auditor", "."]` :
les tests importent `main`, `modules.*`, `kb.*` **sans bootstrap `sys.path` par fichier**. Ne pas
réintroduire de manipulation de `sys.path` dans un test — c'était précisément la dette supprimée.

## Frontend

`npm install` une seule fois, puis `npm run dev` (autoreload) ou `npm run build:kb:web`.
`data.json` est lu **au runtime** : régénérer les données suffit à mettre à jour la KB déployée,
le bundle web n'a besoin d'être rebuild que si `src/` change. Voir [frontend-kb.md](frontend-kb.md).
