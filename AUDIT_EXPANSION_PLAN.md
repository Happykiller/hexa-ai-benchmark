# Plan d'élargissement & consolidation de l'audit

> Statut : proposition — non implémenté. Rédigé le 2026-05-18.
> Objectif : élargir le périmètre de l'auditeur (vertical + horizontal) et consolider l'infrastructure de rapports, sans casser les audits existants.

---

## 1. Diagnostic de départ

### Couverture actuelle

| Bucket | Poids | Indicateurs | Couverture |
|---|---|---|---|
| Opérationnalité | 50% | make targets, E2E (7 steps), Auth E2E (5 steps), perf P95 | bonne |
| Architecture | 25% | hexagonal (5 règles), DI (4), dual-persistence (5) | bonne |
| Qualité logicielle | 15% | `any` count, README (4 sections) | **étroite** |
| Traçabilité | 10% | turns / tool_calls / wall_time | minimale |
| Bonus / Malus | ±5 / ±10 | 5 bonus, 3 malus | minimale |

### Dette identifiée

- **Duplication** : deux dossiers `cr_audits/` (racine + `auditor/`).
- **Couplage `main.py`** : chaque checker est instancié à la main (`main.py:832-839`), aucun registre déclaratif.
- **Pas de comparaison inter-runs** : `knowledge_base/data.json` agrège mais ne calcule pas les deltas par modèle.
- **Auth statique > Auth E2E** : on vérifie qu'une lib JWT est importée, mais pas qu'elle est correctement configurée (algorithm whitelist, secret entropy, expiry).
- **Coverage global** : pas de seuil par couche (`core/` devrait être plus strict que `adapters/`).

---

## 2. Axe vertical — approfondir les piliers existants

### 2.1 Sécurité E2E réelle (priorité haute)

Étendre `AuthTester` dans `auditor/modules/dynamic_analysis.py` avec :

- `test_jwt_alg_none_rejected` — forger un token `{"alg":"none"}` et vérifier rejet 401.
- `test_expired_token_rejected` — utiliser un token expiré (exp < now), vérifier rejet.
- `test_weak_password_rejected` — `register` avec `"123"`, attendre 4xx + message.
- `test_login_rate_limit` — 20 tentatives consécutives en échec, vérifier throttle (429 ou délai).
- `test_password_not_in_response` — `register`/`login` ne renvoient jamais le hash ni le mot de passe.

**Impact scoring** : nouveau step `1-5 "Robustesse sécurité E2E"` avec 5 indicateurs (weights 8/8/5/5/5).

### 2.2 Hexagonal pondéré (priorité moyenne)

Aujourd'hui binaire : OK / KO. Évoluer vers un score continu dans `HexagonalComplianceChecker.check()` :

- `violation_density = violations_count / files_in_layer`
- `core_purity_ratio = pure_files / total_core_files` (pure = aucun import de `node_modules` non-typage)
- `indirection_depth` : nombre moyen de hops d'un usecase vers un adapter.

**Impact scoring** : remplacer `weight=15` binaire par 3 indicateurs continus pondérés via bandes Fibonacci.

### 2.3 Coverage par couche (priorité moyenne)

Parser le rapport Jest par fichier (mode `--coverage --json`) au lieu du tableau ASCII actuel (`main.py:_parse_coverage_results`). Calculer :

- `coverage_core_pct` (seuil cible : ≥85%)
- `coverage_adapters_pct` (seuil cible : ≥60%)
- `coverage_entrypoints_pct` (seuil cible : ≥40%)

**Impact scoring** : 3 indicateurs distincts en `phase 1 step 3`, weight 10/5/3.

### 2.4 E2E métier élargi (priorité basse)

Ajouter à `E2EFunctionalTester.run_scenario()` :

- Chaîne de 3 dépendances (A → B → C, cascade fermeture).
- Fermeture concurrente de 2 tâches sœurs.
- Pagination Relay : 30 tâches, demander `first:10, after:cursor`.
- Filtre : `tasks(status: OPEN)` distingue ouvertes/fermées.

---

## 3. Axe horizontal — nouveaux contrôles

### 3.1 Supply-chain & secrets (priorité haute)

Nouveau module `auditor/modules/supply_chain.py` :

- `NpmAuditChecker` : lance `npm audit --json`, compte CVE high/critical. Malus à partir de 1 critical, -3pts par critical.
- `SecretsScanner` : regex sur clés AWS / GitHub / API keys / `-----BEGIN`. Scanner tout sauf `node_modules`, `dist`, `.git`.
- `GitignoreChecker` : vérifie présence de `.env`, `node_modules`, `dist`, `coverage` dans `.gitignore`.

**Impact scoring** : nouvelle phase 2 step 7 `"Supply-chain & secrets"`, weight total 15.

### 3.2 GraphQL hygiene (priorité moyenne)

Nouveau checker `GraphQLHygieneChecker` :

- Présence de `dataloader` dans deps → bonus N+1.
- Resolver retourne stacktrace en prod ? Grep `formatError|maskedErrors`.
- Schema introspection désactivée en prod ? Grep `introspection:\s*false`.
- Profondeur de query limitée ? Grep `depthLimit|graphql-depth-limit`.

**Impact scoring** : phase 2 step 8, weight 10.

### 3.3 DevEx & CI (priorité moyenne)

Nouveau checker `DevExChecker` :

- `tsconfig.json` : `strict: true`, `noImplicitAny`, `strictNullChecks`.
- `eslint.config.*` ou `.eslintrc.*` présent.
- `.github/workflows/*.yml` présent (CI configurée).
- `.editorconfig`, `prettier` config présents.
- `husky` ou `lefthook` pre-commit.

**Impact scoring** : phase 2 step 9, weight 8.

### 3.4 Migrations DB (priorité basse)

`MigrationChecker` :

- Présence de `src/migrations/` ou `migrations/`.
- Au moins une migration `up`/`down` détectée pour MySQL.
- Script `make migrate` ou équivalent dans `package.json`.

**Impact scoring** : phase 2 step 10, weight 5.

---

## 4. Consolidation infrastructure

### 4.1 Dossier `cr_audits/` unique

- Choisir `cr_audits/` racine comme source unique.
- Migrer le contenu de `auditor/cr_audits/` si non vide.
- Mettre à jour `main.py:1271` (`output_dir = "cr_audits"`) pour utiliser un chemin absolu relatif à la racine du repo, pas au `cwd`.
- Ajouter `.gitkeep` et `.gitignore` filtrant les `.json` non commités si besoin.

### 4.2 Registre déclaratif de checkers

Remplacer dans `main.py` les instanciations manuelles (lignes 832-839) par un registre dans `scoring_config.py` :

```python
CHECKER_REGISTRY = [
    {"id": "hexagonal", "class": HexagonalComplianceChecker, "phase": 2, "step": 1, "step_label": "Conformité hexagonale"},
    {"id": "readme", "class": ReadmeChecker, "phase": 2, "step": 3, "step_label": "Documentation"},
    {"id": "auth_static", "class": AuthImplementationChecker, "phase": 2, "step": 4, "step_label": "Sécurité & Authentification"},
    {"id": "injection", "class": UseCaseInjectionChecker, "phase": 2, "step": 5, "step_label": "Injection de Dépendances"},
    {"id": "dual_persistence", "class": DualPersistenceChecker, "phase": 2, "step": 6, "step_label": "Double Persistance"},
    {"id": "supply_chain", "class": NpmAuditChecker, "phase": 2, "step": 7, "step_label": "Supply-chain"},
    # ...
]
```

Chaque checker expose `.check() -> dict` et un `.to_indicators(result) -> list[Indicator]` standardisé. `main.py` itère le registre.

**Bénéfice** : ajouter un nouvel axe = créer un checker + une entrée. Plus de modification de `main.py`.

### 4.3 Diff inter-runs dans la KB

Étendre `auditor/build_kb.py` :

- Pour chaque modèle, classer les runs chronologiquement.
- Calculer `delta_score = run_n - run_(n-1)` par bucket.
- Identifier les **régressions** : bucket qui baisse de >5% entre deux runs du même modèle.
- Surfacer dans `index.html` une colonne "trend" avec sparkline ou ↑↓.

### 4.4 Schéma JSON versionné pour `audit_trace.json`

Aujourd'hui validé ad-hoc dans `TraceabilityValidator.validate()`. Extraire un JSON Schema `auditor/schemas/audit_trace.v1.json` et utiliser `jsonschema` (déjà transitif via jinja2 ? sinon `pip install jsonschema`).

Permet aux agents de valider leur trace localement avant soumission.

---

## 5. Ordre d'implémentation suggéré

| Phase | Lot | Effort | Impact |
|---|---|---|---|
| 1 | Consolidation dossier `cr_audits/` + registre déclaratif (§4.1, §4.2) | 1j | Débloque le reste |
| 2 | Sécurité E2E réelle (§2.1) | 1j | Corrige faux-positifs critiques |
| 3 | Supply-chain & secrets (§3.1) | 0.5j | Forte différenciation entre modèles |
| 4 | Coverage par couche (§2.3) | 0.5j | Signal architecture |
| 5 | GraphQL hygiene + DevEx (§3.2, §3.3) | 1j | Largeur qualité |
| 6 | Diff inter-runs KB (§4.3) | 0.5j | Visibilité régression |
| 7 | Hexagonal pondéré (§2.2) | 1j | Précision scoring |
| 8 | E2E métier élargi + migrations (§2.4, §3.4) | 1j | Complétude |

Total : ~6.5 jours-personne.

---

## 6. Impact attendu sur la pondération

Si tous les lots sont livrés, les buckets actuels doivent être rééquilibrés pour éviter une explosion de poids. Proposition :

| Bucket | Avant | Après | Justification |
|---|---|---|---|
| Opérationnalité | 50% | 45% | Sécurité E2E élargie absorbe une partie |
| Architecture | 25% | 25% | Compensé par hexagonal pondéré + migrations |
| Qualité (incl. supply-chain, GraphQL, DevEx) | 15% | 20% | Nouveaux contrôles |
| Traçabilité | 10% | 10% | Inchangé |
| Sécurité (nouveau bucket dédié) | — | bonus +5 / malus -10 | Dérivé de §2.1 + §3.1 |

À valider après livraison du lot 3 (premières données réelles).

---

## 7. Risques

- **Stabilité historique** : changer la pondération invalide les comparaisons avec les 7 runs déjà capturés (`cr_audits/cr_2026*`). Mitigation : versionner le `scoring_model` (actuellement `indicator_fibonacci_v1`) → `v2`, et conserver les deux exécutions possibles via flag CLI `--scoring v1|v2`.
- **`npm audit` flaky** : dépendant du registry public. Mitigation : timeout 30s, fallback "SKIPPED" sans pénalité.
- **Faux-positifs secrets scanner** : regex large. Mitigation : whitelist `.env.example`, fixtures de test.
- **Coverage par couche** : nécessite que Jest émette `--coverage --json --coverageReporters=json-summary`, certains livrables ne le configurent pas. Mitigation : fallback sur le tableau ASCII actuel.
