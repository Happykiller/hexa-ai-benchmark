# Hexa-AI Benchmark

Framework d'évaluation industrielle de la capacité des agents IA à livrer des solutions logicielles **opérationnelles**, **architecturalement robustes** et **professionnelles**.

---

## Objectifs

Le benchmark mesure cinq piliers (scoring **v2**, défaut depuis le 2026-06-08) :

| Pilier | Poids | Ce qui est évalué |
|---|---|---|
| Opérationnalité | 43% | Build, tests, Docker, E2E fonctionnel, auth E2E, couverture |
| Architecture | 22% | Hexagonal, auth statique, injection de dépendances, double persistance |
| Qualité logicielle | 13% | Typage TypeScript (`any`), documentation README |
| Discipline & Traçabilité | 10% | `audit_trace.json` valide, efficacité de session |
| Coût & Efficience | 12% | Coût $ de la session = tokens déclarés × table de prix de l'auditeur |

Les poids historiques **50 / 25 / 15 / 10 sans pilier Coût** sont le scoring **v1**, conservé pour
rejouer à l'identique les runs d'avant juin : `--scoring v1`. Les deux jeux de poids sont dans
`hexa/benches/todo/auditor/scoring_config.py`, et chaque entrée de la KB porte le modèle qui l'a produite
(`fib_v1` / `fib_v2`) — **des scores v1 et v2 ne sont pas directement comparables**.

Un bonus/malus s'applique par-dessus les piliers (+5 max / -10 max) pour les initiatives proactives
et l'over-engineering détecté. En v2 il n'est **pas** symétrique : les malus se soustraient en
plein, puis le bonus ne comble que **la moitié de l'écart restant à 100 %**
(`BONUS_HEADROOM_FRACTION`). Un livrable imparfait s'approche de 100 % sans jamais l'atteindre —
100 % est réservé à une base sans défaut.

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
├── hexa/                          # Code Python — `python3 -m hexa --help`
│   ├── cli.py  paths.py           # CLI unique ; TOUS les chemins du dépôt
│   ├── core/                      # Commun à tous les benchmarks
│   │   ├── engine/                # Notation : indicateurs Fibonacci, piliers, caps, trace, coût
│   │   ├── kb/                    # Magasin KB générique (KbStore, overrides, cartes communes)
│   │   └── tools/session_usage.py # Usage réel d'une session (tokens, effort) vs audit_trace.json
│   └── benches/                   # Un dossier = un benchmark autonome
│       ├── todo/                  # API Todo hexagonale (TypeScript/GraphQL)
│       │   ├── auditor/           # main.py, challenges.py, scoring_config.py, modules/, templates/
│       │   ├── enonce/            # evaluation_prompt.md remis aux agents
│       │   ├── kb/                # Normalisation et cartes de la KB Todo
│       │   └── tests/
│       └── blender/               # Créature 3D riggée et animée (Blender)
│           ├── auditor/           # cli.py, analysis/, bench_config.py, runner.py, templates/
│           ├── bpy/               # Scripts exécutés DANS Blender (mesures, rendus)
│           ├── challenges/<id>/   # concept.png + enonce.md + spec.json
│           ├── kb/                # Normalisation, cartes et visuels de la KB Blender
│           └── tests/
├── web/                           # Front React/Vite unique (src/, index.html, vite.config.js)
├── sites/<bench>/                 # KB publiées : data.json, bundle, médias (versionné)
├── runs/<bench>/                  # NON versionné
│   ├── livrables/                 # Dossiers soumis par les agents
│   └── cr_audits/                 # Rapports bruts .json/.md (source immuable)
├── docs/KB/                       # Base de connaissance du projet (mémoire longue)
├── .claude/                       # Outillage agent versionné : skills/, agents/, hooks/
└── requirements.txt  package.json pyproject.toml
```

Ajouter un benchmark = ajouter `hexa/benches/<nom>/` (auditeur, énoncé, KB, tests) et l'enregistrer
dans `hexa/cli.py` et `hexa/paths.py` ; le noyau et le front ne changent pas.

---

## Lancer un audit

```bash
# Installation (une seule fois)
python3.11 -m venv venv && source venv/bin/activate   # Python ≥ 3.10 requis
pip install -r requirements.txt

# Machine qui avait l'ancienne arborescence (livrables/, cr_audits/… à la racine) : une fois
python3 -m hexa migrate-layout --dry-run && python3 -m hexa migrate-layout

# Audit complet (démarre Docker, exécute l'E2E)
python3 -m hexa todo analyze runs/todo/livrables/<NOM_DU_LIVRABLE>

# Recouper les métriques auto-déclarées (tokens, modèle, effort, durée) avec le transcript
python3 -m hexa usage ~/.claude/projects/<cwd-encodé>/<session>.jsonl \
  --trace runs/todo/livrables/<NOM_DU_LIVRABLE>/audit_trace.json
```

**Options de `analyze` :**

| Option | Effet |
|---|---|
| `--skip-dynamic` | Saute Docker, E2E, auth E2E et benchmark de perf |
| `--force-dynamic` | Lance `make test`, Docker, E2E et perf **même si `make build` échoue** |
| `--fresh-docker` | `docker compose down -v` avant `make start` (repart de volumes vides) |
| `--scoring v1\|v2` | Règle de plafond du score final (défaut `v2` ; `v1` rejoue les scores historiques) |

> ⚠️ **`--skip-dynamic` n'est pas un mode « sans Docker ».** `make setup`, `make lint`, `make build`
> et `make test` s'exécutent quand même — or ces cibles passent par Docker dans le contrat livrable.
> Sur une machine sans démon Docker, `make build` échoue et **le run est plafonné à 40 %**, ce qui
> ressemble à un mauvais livrable. `--skip-dynamic` ne saute que la stack démarrée, l'E2E et la perf.

> ⚠️ **Ne jamais lancer un audit pendant qu'une session d'agent tourne encore** sur la machine :
> elle occupe les mêmes ports (4000 / 47017 / 43306) et l'auditeur sonderait l'API de l'agent,
> puis détruirait sa stack au teardown (loi n°10).

**Sorties générées :**
- `runs/todo/cr_audits/cr_<nom>_<timestamp>.md` — rapport lisible
- `runs/todo/cr_audits/cr_<nom>_<timestamp>.json` — données brutes d'audit
- `<livrable>/audit_report_<timestamp>.md` — copie dans le dossier du livrable

`HEXA_AUDIT_OUTPUT_DIR` redirige les deux premières sorties ailleurs que dans `runs/todo/cr_audits/` (utile
pour un run de test qu'on ne veut pas voir remonter dans la KB) ; `HEXA_AUDIT_LOG_LEVEL` règle la
verbosité.

---

## Benchmark Blender 3D (second défi)

Un agent reçoit une planche concept (`hexa/benches/blender/challenges/<défi>/concept.png`) et un
énoncé (`enonce.md`), et livre un `build.py` qui construit dans Blender une créature riggée et
animée. L'auditeur le rejoue dans Blender 4.5 headless puis note le résultat (barème b1).
Détails : [`docs/KB/DAT/blender-pipeline.md`](docs/KB/DAT/blender-pipeline.md).

```bash
# Audit (Blender : --blender, $HEXA_BLENDER_BIN, `blender` du PATH ou ~/.local/bin/blender45)
python3 -m hexa blender analyze runs/blender/livrables/<NOM_DU_LIVRABLE>

# Itérer sans rendus (score non publiable) / réanalyser sans relancer Blender
python3 -m hexa blender analyze runs/blender/livrables/<NOM> --skip-render --keep-work
python3 -m hexa blender analyze runs/blender/livrables/<NOM> --reuse-work /tmp/hexa_blender_xxx

# KB Blender (site séparé : sites/blender/)
python3 -m hexa kb blender --add runs/blender/cr_audits/cr_<...>.json
npm run build:web:blender

# Tests de rendu (≈ 1 min) en plus de la suite
HEXA_BLENDER_SLOW=1 pytest -q hexa/benches/blender
```

Sorties : `runs/blender/cr_audits/cr_<nom>_<ts>.{json,md}` + `cr_<…>_media/` (rendus, silhouettes
superposées au concept, turntable MP4, planches d'animation).

> ⚠️ L'auditeur **exécute** `build.py` sur l'hôte, sous garde-fous mais sans isolation forte :
> n'auditer que des livrables issus de nos propres sessions (loi n°11).

---

## Mettre à jour la knowledge base

La KB est un **magasin de données** dérivé, pas un simple snapshot :

- `runs/todo/cr_audits/*.json` (+ `.md` jumeaux) = **source brute immuable** produite par l'auditeur.
- `sites/todo/overrides.json` = **corrections manuelles tracées/réversibles**, keyées par
  id d'entrée (ex. `model`/`effort` mal auto-déclarés par l'agent — voir « Format
  `audit_trace.json` »). Appliquées au build ; jamais hand-editer les `cr_*.json`.
- `sites/todo/data.json` = **dérivé** (brut + overrides), régénérable **ou** upsertable
  à l'unité. Le coût estimé ($, tokens, pts/$) y est surfacé et affiché dans le détail ;
  les entrées corrigées portent une section « Corrections manuelles ».

> ⚠️ **`runs/todo/cr_audits/` n'est pas versionné, `data.json` l'est.** Un rapport brut supprimé, ou produit
> sur une autre machine, rend son entrée publiée irrécupérable par un rebuild complet. Le builder
> **refuse donc d'écrire** si le rebuild ferait disparaître des entrées déjà publiées, et liste
> lesquelles. Dans ce cas : restaurer les `cr_*.json` manquants, ou passer par `--add`. `--allow-drop`
> force la suppression — à ne faire qu'après avoir relu `git diff sites/todo/data.json`.

```bash
python3 -m hexa kb todo --add runs/todo/cr_audits/cr_<...>.json   # VOIE PAR DÉFAUT : ajout/maj d'UNE entrée (upsert par id)
python3 -m hexa kb todo                     # rebuild complet — refusé s'il ferait perdre des entrées publiées
python3 -m hexa kb todo --allow-drop        # rebuild complet EN ACCEPTANT de perdre des entrées

# Corriger une métadonnée : éditer sites/todo/overrides.json, ex.
#   { "cr_20260529_1322_GPT5.5-medium_20260529_161440": { "model": "gpt-5.4-codex" } }
# puis relancer build_kb.py --add. Un override est cosmétique : il ne recalcule ni coût ni score.

npm ci                           # une seule fois (rendu web ; data.json est lu au runtime)
npm run dev                      # serveur React/Vite en dev avec autoreload
npm run build:web:todo             # régénère sites/todo/index.html et assets/
git add sites/todo/ && git commit -m "kb: add run <agent> <date>"
```

`runs/todo/cr_audits/` n'est **pas versionné** : sur une machine donnée, la plupart des entrées publiées n'ont
pas leur `cr_*.json`. Un rebuild complet les effacerait de `data.json` — le builder le refuse
(exit 1 + liste des entrées concernées, `--allow-drop` pour passer outre). Les scripts npm ne touchent plus aux données : `npm run build:web` ne construit que le bundle.

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

**Phase 5 — Statistiques techniques**
- Mesures du codebase rangées en bandes : nombre de fichiers, fichiers TS, LOC, fichiers de tests
- Ces indicateurs sont **hors buckets** : ils informent le rapport sans peser sur les cinq piliers

**Phase 6 — Coût & Efficience** (scoring v2)
- Coût $ de la session = tokens déclarés dans `audit_trace.json` × `MODEL_PRICING`
- Bandes : ≤ $0.50 = 100 %, ≤ $1.50 = 75 %, ≤ $3 = 50 %, ≤ $6 = 25 %, au-delà 0
- Modèle absent de la table de prix ⇒ repli sur le **nombre total de tokens** (mêmes paliers en volume), pour ne pas pénaliser l'agent d'une lacune de l'opérateur
- Tokens absents du `audit_trace.json` ⇒ **0 sur les 12 %** du pilier

---

## Format `audit_trace.json`

L'agent doit fournir un fichier `audit_trace.json` à la racine de son livrable :

```json
{
  "meta": {
    "prompt_version": "2606082200",
    "model": "claude-sonnet-4-6"
  },
  "summary": {
    "total_turns": 12,
    "total_tool_calls": 45,
    "total_wall_time_seconds": 1240,
    "total_input_tokens": 200000,
    "total_output_tokens": 50000,
    "total_cached_input_tokens": 0
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

`total_input_tokens` / `total_output_tokens` / `total_cached_input_tokens` alimentent le pilier
Coût : **les omettre coûte les 12 % de ce pilier**. C'est l'agent qui déclare ces compteurs — le
prix, lui, vient de la table de l'auditeur, donc le montant $ n'est pas auto-déclarable. Voir
[`docs/KB/DAF/tracabilite-agent.md`](docs/KB/DAF/tracabilite-agent.md) sur la portée exacte de
l'auto-déclaration.

La référence normative remise aux agents reste [`hexa/benches/todo/enonce/evaluation_prompt.md`](hexa/benches/todo/enonce/evaluation_prompt.md) :
en cas de divergence avec ce README, c'est l'énoncé qui fait foi.

---

## Seuil d'admission

**Score ≥ 60%** — ADMIS  
**Score < 60%** — ÉCHEC
