---
titre: Contrat du livrable — ce que l'auditeur exige
type: dat
statut: actif
maj: 2026-09-04
---

# Contrat du livrable

Ce que l'auditeur **suppose** de tout dossier de `livrables/`. Ce contrat est implicite dans le
code des checkers : le violer ne produit pas une erreur claire, mais un score bas difficile à
diagnostiquer.

## Cibles `make` appelées séquentiellement

| Cible | Rôle attendu |
|---|---|
| `make setup` | Installer les dépendances (une fois, avant `make start`) |
| `make lint` | ESLint + Prettier via Docker |
| `make build` | Compilation TypeScript via Docker |
| `make test` | Tests Jest unitaires/intégration via Docker |
| `make start` | Démarrer Docker Compose (API + MongoDB + MySQL) |
| `down` / `stop` / `clean` / `teardown` / `destroy` | Cible de **teardown** contenant `docker compose down` — scorée par `MakefileTeardownChecker` |

`make build` en échec ⇒ score plafonné à 40 % (voir
[`../DAF/piliers-notation.md`](../DAF/piliers-notation.md)).

## Structure attendue

```
livrables/<HORODATAGE_MODELE_EFFORT>/
├── audit_trace.json          # dont les compteurs de tokens (pilier Coût)
├── Makefile                  # + une cible de teardown
├── docker-compose.yml        # services : api, mongodb, mysql (sans champ version:, ports hôte 4000 / 47017 / 43306)
├── package.json
├── tsconfig.json             # strict requis — et réellement activé, pas juste présent
├── src/{core,adapters,infrastructure,entrypoints}/
└── README.md                 # sections Architecture, Installation, API, Docker
```

## Ports hôte imposés

`ComposePortsChecker` vérifie le mapping exact déclaré dans le profil de défi
(`db_port_contract`) :

| Service | Mapping attendu |
|---|---|
| `mongodb` | `47017:27017` |
| `mysql` | `43306:3306` |

Ces ports décalés évitent de heurter une base déjà lancée sur la machine d'audit. L'API, elle,
joint les bases par **nom de service compose** sur le réseau interne (`mongodb:27017`,
`mysql:3306`) — jamais par `localhost`.

## Les cinq hypothèses dures

1. **`src/core/` n'importe rien** de `adapters/`, `infrastructure/` ou `entrypoints/`. C'est *la*
   mesure de conformité hexagonale ; toute violation est comptée comme échec architectural.
2. **L'endpoint GraphQL est `http://localhost:4000/graphql`**, en dur dans le profil de défi. Un
   livrable qui écoute ailleurs échoue toute la phase dynamique, quelle que soit sa qualité.
3. **`audit_trace.json` est présent et bien formé** (datetimes ISO-8601, pourcentages de contexte).
   Absent ou malformé ⇒ 0 sur la phase 3. Sur sa fiabilité, voir
   [`../DAF/tracabilite-agent.md`](../DAF/tracabilite-agent.md).
4. **Le README a du contenu réel** sous chaque section requise — un titre vide ne compte pas. Le
   checker vérifie la substance, pas la présence du heading.
5. **`summary` porte les compteurs de tokens** (`total_input_tokens`, `total_output_tokens`,
   `total_cached_input_tokens`). Leur absence ⇒ 0 sur le pilier Coût, soit **12 % perdus** sans
   qu'aucun contrôle technique n'ait échoué. C'est le piège le plus coûteux du contrat, parce
   qu'il ne ressemble pas à un défaut du code.

## Détails qui piègent

- L'attribut `version` dans `docker-compose.yml` est **obsolète** : sa présence est détectée dans
  la sortie Compose et pénalisée.
- La détection du `any` TypeScript attrape aussi `as any` et `<any>`, en excluant les commentaires.
  Contourner par une forme exotique n'est pas prévu — et serait du gaming.
- Les bind-mounts déclarés dans le compose (typiquement `./coverage`) sont pré-créés par
  l'auditeur : voir [environnements.md](environnements.md) pour la raison.

L'énoncé remis aux agents (`prompts/evaluation_prompt.md`) est la version *lisible* de ce contrat.
S'ils divergent, c'est l'énoncé qui doit être corrigé — un agent ne peut pas satisfaire une
exigence qu'on ne lui a pas donnée.
