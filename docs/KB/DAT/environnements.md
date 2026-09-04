---
titre: Environnements — installer, lancer, tester
type: dat
statut: actif
maj: 2026-09-04
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
- `--skip-dynamic` **ne retire pas le besoin de Docker.** Il saute la stack démarrée, l'E2E et la
  perf, mais `make setup|lint|build|test` s'exécutent quand même — et ces cibles passent par Docker
  dans le contrat livrable. Sans démon Docker, `make build` échoue et le run est plafonné à 40 %.
  C'est le mode pour itérer sur les checkers sans payer les minutes d'E2E, pas un mode hors-ligne.

## Piège n°0 — un cap à 40 % venu de l'environnement

Trois mécanismes distincts produisent un 40 % qui ne dit rien du livrable : l'absence de Docker
avec `--skip-dynamic` (ci-dessus), les bind-mounts `root:root` (piège n°2), et un port 4000 déjà
occupé. Avant de publier un run à 40 %, écarter les trois — c'est une loi du projet, voir
[`../REGLES/lois.md`](../REGLES/lois.md).

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

## Piège n°3 — un audit laisse sa stack en vie

Un audit ne fait pas de `docker compose down` en sortie : la stack du livrable **continue de
tourner** après la fin du run. Le nom du projet compose est celui du dossier de livrable
(ex. `20260702_0705_claude-fable-5_10`), pas celui de ce dépôt.

Deux raisons pour lesquelles ça passe inaperçu :

1. `livrables/` et `cr_audits/` sont gitignorés, donc **le working tree reste propre** — rien ne
   signale qu'un audit a eu lieu, encore moins qu'il a laissé quelque chose derrière lui ;
2. même un audit `--skip-dynamic` en laisse, puisque les cibles `make` passent par Docker.

Le contrôle est `docker compose ls` : toute stack dont le `CONFIG FILES` pointe dans `livrables/`
est un résidu. C'est l'étape 6 du skill `/cloture`, et la raison pour laquelle un dépôt propre ne
suffit pas à déclarer une session close.

## Tests de l'auditeur

`pyproject.toml` déclare `testpaths = ["auditor/tests"]` et un `pythonpath = ["auditor", "."]` :
les tests importent `main`, `modules.*`, `kb.*` **sans bootstrap `sys.path` par fichier**. Ne pas
réintroduire de manipulation de `sys.path` dans un test — c'était précisément la dette supprimée.

## Frontend

`npm install` une seule fois, puis `npm run dev` (autoreload) ou `npm run build:kb:web`.
`data.json` est lu **au runtime** : régénérer les données suffit à mettre à jour la KB déployée,
le bundle web n'a besoin d'être rebuild que si `src/` change. Voir [frontend-kb.md](frontend-kb.md).
