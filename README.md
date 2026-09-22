# Hexa-AI Benchmark

Framework d'évaluation industrielle de la capacité des agents IA à livrer des solutions logicielles **opérationnelles**, **architecturalement robustes** et **professionnelles**.

---

## Objectifs

Le benchmark mesure quatre piliers :

| Pilier | Poids | Ce qui est évalué |
|---|---|---|
| Opérationnalité | 50% | Build, tests, Docker, E2E fonctionnel, auth E2E, couverture |
| Architecture | 25% | Hexagonal, auth statique, injection de dépendances, double persistance |
| Qualité logicielle | 15% | Typage TypeScript (`any`), documentation README |
| Discipline & Traçabilité | 10% | `audit_trace.json` valide, efficacité de session |

Un bonus/malus (+5 max / -10 max) s'applique en sus pour les initiatives proactives et les over-engineering détectés.

---

## Le défi imposé aux agents

Une **Todo List Multi-Bases** en TypeScript / GraphQL :

- **Core Domain** : entités, use cases, ports — isolés de toute infrastructure
- **Adapters** : double persistance **MongoDB** (tasks) + **MySQL** (users/auth)
- **Entrypoints** : API **GraphQL** avec authentification **JWT**
- **Dependency Injection** : **InversifyJS** (`@injectable`, `@inject`)
- **Containerisation** : **Docker Compose** opérationnel via `make start`
- **Logique métier** : graphe de dépendances entre tâches (blocage si pré-requis non terminés)

---

## Structure du dépôt

```
hexa-ai-benchmark/
├── auditor/              # Moteur d'audit Python
│   ├── main.py           # CLI principal (commande analyze)
│   ├── scoring_config.py # Poids, bandes de score, caps
│   ├── challenges.py     # Profil de défi + registre déclaratif de checkers statiques
│   ├── modules/
│   │   ├── static_analysis.py   # Checkers hexagonal, auth, DI, double persistance
│   │   ├── dynamic_analysis.py  # Docker, E2E GraphQL, auth E2E sécurité, perf
│   │   └── supply_chain.py      # DevEx, scan de secrets, npm audit
│   └── tests/
├── scripts/
│   └── build_kb.py       # Wrapper CLI du builder de knowledge base
├── kb/
│   ├── __init__.py
│   ├── builder.py        # Orchestration du build des données statiques de KB
│   ├── constants.py      # Chemins et constantes partagées
│   ├── markdown_parser.py# Extraction des constats depuis les rapports .md
│   ├── normalizer.py     # Chargement et normalisation des audits JSON/MD
│   └── render.py         # Sections normalisées consommées par le frontend React
├── src/                  # Frontend React/Vite pour l'affichage de la KB
├── package.json          # Scripts npm de build du frontend KB
├── vite.config.js        # Build du frontend vers knowledge_base/
├── cr_audits/            # Rapports JSON/MD des audits lancés depuis la racine
├── knowledge_base/
│   ├── index.html        # Build React statique
│   ├── assets/           # Bundles front générés par Vite
│   └── data.json         # Entrées normalisées de tous les audits
├── livrables/            # Dossiers soumis par les agents
└── prompts/              # Prompt d'évaluation remis aux agents
```

---

## Lancer un audit

```bash
# Installation (une seule fois)
python3.11 -m venv venv && source venv/bin/activate   # Python ≥ 3.10 requis
pip install -r auditor/requirements.txt

# Audit complet (démarre Docker, exécute l'E2E)
python3 auditor/main.py analyze livrables/<NOM_DU_LIVRABLE>

# Audit statique uniquement (pas de stack démarrée — make lint/build/test passent quand même par Docker)
python3 auditor/main.py analyze livrables/<NOM_DU_LIVRABLE> --skip-dynamic

# Recouper les métriques auto-déclarées (tokens, modèle, effort, durée) avec le transcript
python3 scripts/session_usage.py ~/.claude/projects/<cwd-encodé>/<session>.jsonl \
  --trace livrables/<NOM_DU_LIVRABLE>/audit_trace.json
```

> Ne jamais lancer un audit pendant qu'une session d'agent tourne encore sur la machine : elle
> occupe les mêmes ports (4000 / 47017 / 43306) et l'auditeur sonderait l'API de l'agent.

**Sorties générées :**
- `cr_audits/cr_<nom>_<timestamp>.md` — rapport lisible
- `cr_audits/cr_<nom>_<timestamp>.json` — données brutes d'audit
- `<livrable>/audit_report_<timestamp>.md` — copie dans le dossier du livrable

---

## Mettre à jour la knowledge base

La KB est un **magasin de données** dérivé, pas un simple snapshot :

- `cr_audits/*.json` (+ `.md` jumeaux) = **source brute immuable** produite par l'auditeur.
- `knowledge_base/overrides.json` = **corrections manuelles tracées/réversibles**, keyées par
  id d'entrée (ex. `model`/`effort` mal auto-déclarés par l'agent — voir « Format
  `audit_trace.json` »). Appliquées au build ; jamais hand-editer les `cr_*.json`.
- `knowledge_base/data.json` = **dérivé** (brut + overrides), régénérable **ou** upsertable
  à l'unité. Le coût estimé ($, tokens, pts/$) y est surfacé et affiché dans le détail ;
  les entrées corrigées portent une section « Corrections manuelles ».

```bash
python3 scripts/build_kb.py --add cr_audits/cr_<...>.json   # VOIE PAR DÉFAUT : ajout/maj d'UNE entrée (upsert par id)
python3 scripts/build_kb.py                     # rebuild complet — refusé s'il ferait perdre des entrées publiées
python3 scripts/build_kb.py --force             # rebuild complet même en perdant des entrées (à éviter)

# Corriger une métadonnée : éditer knowledge_base/overrides.json, ex.
#   { "cr_20260529_1322_GPT5.5-medium_20260529_161440": { "model": "gpt-5.4-codex" } }
# puis relancer build_kb.py --add. Un override est cosmétique : il ne recalcule ni coût ni score.

npm ci                           # une seule fois (rendu web ; data.json est lu au runtime)
npm run dev                      # serveur React/Vite en dev avec autoreload
npm run build:kb:web             # régénère knowledge_base/index.html et assets/
git add knowledge_base/ && git commit -m "kb: add run <agent> <date>"
```

`cr_audits/` n'est **pas versionné** : sur une machine donnée, la plupart des entrées publiées n'ont
pas leur `cr_*.json`. Un rebuild complet les effacerait de `data.json` — le builder le refuse
(exit 2 + liste des entrées concernées). `npm run build:kb` / `dev:kb` enchaînent ce même rebuild.

Format d'`overrides.json` : `{ "<id_entrée>": { "<champ>": "<valeur>" } }` — merge shallow
au niveau top de l'entrée (`model`, `effort`, `prompt_version`, …). Le rendu web lit
`data.json` au runtime : régénérer `data.json` suffit à mettre à jour la KB déployée.

---

## Modèle de scoring (`indicator_fibonacci_v2`)

Chaque vérification produit un **indicateur** pondéré selon la séquence de Fibonacci (position dans l'étape). Les indicateurs sont agrégés en buckets normalisés sur 100 points.

### Caps automatiques

| Condition | Score plafonné à |
|---|---|
| `make build` échoue | 40% |
| Scénario E2E fonctionnel échoue | 40% |
| Stack non démarrée (`make start` / santé GraphQL KO) : scénario E2E non exécuté | 40% |

### Ce que l'auditeur vérifie

**Phase 1 — Opérationnalité**
- `make setup / lint / build / test` — build propre et tests passants
- Parsing des résultats Jest : tests passés/échoués, couverture (`--coverage`)
- Démarrage Docker via `make start` avec health-check GraphQL
- Scénario E2E : création de tâches liées, blocage par dépendances, fermeture en cascade
- Scénario auth E2E : accès non-authentifié bloqué, register/login JWT, token falsifié rejeté
- Sécurité E2E approfondie : `alg:none` rejeté, signature étrangère rejetée, isolation inter-utilisateurs, code `UNAUTHENTICATED` exact, mot de passe faible refusé
- Tâche sans dépendance fermable (anti-triche « always-block »)
- Benchmark de latence (50 requêtes, P95)

**Phase 2 — Architecture & Qualité**
- Conformité hexagonale : pas d'import `adapters/infrastructure/entrypoints` depuis `core`
- Qualité de typage : occurrences de `any` dans les fichiers `.ts/.tsx`
- README : sections architecture, installation, API GraphQL, Docker (présence **et contenu réel**)
- Auth statique : bibliothèque JWT, mutations register/login, guard, hachage de mot de passe
- Injection de dépendances : `@injectable`, `@inject`, pas d'instanciation directe dans Core
- Double persistance : Mongoose (tasks) + ORM SQL (users/auth), adaptateurs séparés
- DevEx & outillage : `tsconfig strict` réellement activé, ESLint, CI (`.github/workflows`), `.gitignore`

**Phase 3 — Traçabilité**
- Présence et validité du fichier `audit_trace.json` fourni par l'agent
- Cohérence summary vs phases (écart toléré : 10%)
- Métriques d'efficacité : nombre de turns (cible 5–15), tool calls (20–60), wall time (10–30 min)

**Phase 4 — Bonus / Malus**
- Bonus : gestion d'erreurs centralisée, validation d'env (zod/envalid), healthcheck, pagination Relay, logger structuré
- Malus : AbstractFactory (over-abstraction), fragmentation extrême (>30% de fichiers < 10 lignes), attribut `version` Docker obsolète, fichiers vides/placeholder, tests sans assertion ou non exécutés, secrets/`.env` commités, vulnérabilités npm high/critical

---

## Format `audit_trace.json`

L'agent doit fournir un fichier `audit_trace.json` à la racine de son livrable :

```json
{
  "meta": {
    "prompt_version": "2605291055",
    "model": "claude-sonnet-4-6"
  },
  "summary": {
    "total_turns": 12,
    "total_tool_calls": 45,
    "total_wall_time_seconds": 1240
  },
  "phases": [
    {
      "start_time": "2026-04-24T10:00:00Z",
      "end_time": "2026-04-24T10:18:00Z",
      "turns_in_phase": 6,
      "tool_calls_in_phase": 22
    }
  ]
}
```

Les valeurs du `summary` doivent être cohérentes avec la somme des phases (tolérance ±10%).

---

## Seuil d'admission

**Score ≥ 60%** — ADMIS  
**Score < 60%** — ÉCHEC
