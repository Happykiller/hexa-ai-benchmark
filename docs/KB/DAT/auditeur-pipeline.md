---
titre: Pipeline d'audit — phases, checkers et parti pris
type: dat
statut: actif
maj: 2026-09-23
---

# Pipeline d'audit

`auditor/main.py` est l'orchestrateur. Il alimente une structure `audit_db` imbriquée
(phases → étapes → indicateurs), finalise en calculant les scores pondérés
(`_finalize_audit_db()`), puis rend `auditor/templates/report.md` via Jinja2.

## Les six phases du rapport

| # | Phase | Contenu | Pèse dans le score ? |
|---|---|---|---|
| 1 | Opérationnalité | cibles `make`, Docker, E2E fonctionnel, auth E2E, perf | oui (43 %) |
| 2 | Architecture & Qualité | hexagonal, auth statique, DI, double persistance, README, `any`, DevEx | oui (22 % + 13 %) |
| 3 | Traçabilité | lecture de l'`audit_trace.json` fourni par l'agent | oui (10 %) |
| 4 | Bonus / Malus | initiatives proactives, over-engineering, secrets, npm audit | hors buckets (+5 / −10) |
| 5 | Statistiques techniques | mesures du codebase rangées en bandes | non, informatif |
| 6 | Coût & Efficience | tokens déclarés × `MODEL_PRICING` | oui (12 %, scoring v2) |

La phase 2 alimente **deux** buckets : les étapes 1, 4, 5, 6 vont dans *Architecture*, les étapes
2, 3, 7 dans *Qualité logicielle* (voir les `selectors` de `BASE_SCORE_BUCKETS_V2`).

## L'ordre d'exécution réel

Attention au contre-intuitif : **le dynamique s'exécute avant le registre statique**.

1. Pré-création des bind-mounts (voir [environnements.md](environnements.md))
2. `make setup`, `make lint`, `make build` — **inconditionnels**
3. `make test` — si `make build` est OK (ou `--force-dynamic`)
4. Docker, E2E fonctionnel, auth E2E, perf, E2E adversarial — sautés par `--skip-dynamic`
5. Puis seulement le registre des checkers statiques, la phase 6 (coût) et les stats

Conséquence pratique : `--skip-dynamic` **n'est pas un mode « sans Docker »**. Les cibles `make`
passent par Docker dans le contrat livrable, donc sans démon Docker `make build` échoue et le run
est plafonné à 40 % — un faux négatif qui ressemble à un mauvais livrable.

## Checkers statiques — `modules/static_analysis.py`

| Checker | Ce qu'il mesure | Point de vigilance |
|---|---|---|
| `HexagonalComplianceChecker` | Isolation des couches (Core n'importe pas d'ailleurs) **et** `core_purity_ratio`, un signal continu récompensant un domaine sans lib d'infra | Strippe les commentaires par regex avant de scanner les imports — sinon un import commenté compterait. La pureté continue existe pour dé-saturer un contrôle sinon binaire |
| `AuthImplementationChecker` | Bibliothèque JWT, mutations register/login, guard, hachage de mot de passe | Un des plus lourds en poids |
| `UseCaseInjectionChecker` | `@injectable`, `@inject`, constructeurs recevant leurs dépendances, pas d'instanciation directe dans Core | — |
| `DualPersistenceChecker` | Mongoose côté tasks, ORM SQL côté users/auth, adaptateurs séparés | Vérifie l'usage réel dans le code, pas seulement la présence en dépendance |
| `CodeQualityChecker` | Occurrences de `any` TypeScript | Score inverse : 100 − count×2 |
| `ProjectStatsAnalyzer` | Fichiers, TS/TSX, LOC, tests, taille | Alimente `TECHNICAL_STATS_SCORING_CONFIG` (phase 5, non scorée) |
| `CodeSmellAnalyzer` | Bonus (erreurs custom, validation d'env, healthcheck, pagination Relay, log structuré) et malus (AbstractFactory, fragmentation extrême >30 % de fichiers <10 lignes) | Le malus de fragmentation existe pour punir le découpage cosmétique |
| `ReadmeChecker` | Sections requises **avec contenu réel** | Un heading vide ne rapporte rien |

`modules/supply_chain.py` ajoute :

- `DevExChecker` — tsconfig `strict` réellement activé, ESLint, CI, `.gitignore` sain ;
- `SecretsScanner` et `NpmAuditChecker` — en malus ;
- `ComposePortsChecker` — les ports hôte du contrat (`47017:27017`, `43306:3306`) ;
- `MakefileTeardownChecker` — une cible `down|stop|clean|teardown|destroy` contenant
  `docker compose down`.

Ces deux derniers sont **statiques et toujours exécutés** : ils notent le contrat de déploiement
sans avoir besoin de Docker.

## Checkers dynamiques — `modules/dynamic_analysis.py`

| Checker | Ce qu'il fait |
|---|---|
| `MakefileRunner` | Exécute une cible make (timeout 5 min), capture stdout/stderr et code retour |
| `DockerOrchestrator` | Démarre la stack, sonde la santé (max **60 essais × 2 s = 120 s**, budget élargi pour l'init à froid du volume MySQL 8.4), lit l'état des conteneurs |
| `E2EFunctionalTester` | Scénario GraphQL de blocage par dépendances, **plus** un scénario **adversarial** (`run_adversarial_scenario()`) : dépendances multiples, chaîne profonde, dépendance inexistante, statut invalide |
| `AuthTester` | Auth + sécurité réelle : `alg:none` rejeté, signature étrangère rejetée, isolation inter-utilisateurs, code `UNAUTHENTICATED` exact, mot de passe faible refusé — JWT forgés avec la stdlib, sans dépendance ajoutée |
| `PerformanceBenchmarker` | 50 requêtes GraphQL : latence moyenne, P95, taux d'erreur |

## Parti pris : orchestrateur challenge-agnostique

`auditor/challenges.py` isole tout ce qui est spécifique au défi Todo (endpoint GraphQL, noms et
poids des étapes E2E, noms de couches) dans un `ChallengeProfile`. `TODO_STATIC_CHECKERS` est un
**registre déclaratif** : chaque checker porte son mapper `emit`, qui réutilise `_append_indicator`.

Conséquence pratique, et c'est le point à retenir : **ajouter un contrôle statique = une entrée de
registre, sans toucher à `main.py`**. Un changement qui modifie `main.py` pour ajouter un checker
rate l'intention de l'architecture.

Le moteur de notation lui-même (indicateurs Fibonacci, piliers, caps, traçabilité, coût) vit
dans `auditor/engine/`, sans rien de propre au défi : `_finalize_audit_db` reçoit un barème en
paramètre. C'est ce qui permet au benchmark Blender ([blender-pipeline](blender-pipeline.md)) de
réutiliser phases 3 et 6 à l'identique. `auditor/tests/test_engine_regression.py` rejoue des
rapports publiés (v1, v2, v2 plafonné) : toute modification du moteur doit le laisser vert.

## Anti-triche

Plusieurs contrôles existent uniquement pour empêcher un agent de gagner des points sans
implémenter la logique. Le plus explicite : dans l'E2E de dépendances, fermer « B alors que A est
ouverte » doit échouer avec un message contenant `depend|blocked|prerequisite|precondition`,
**et** une tâche sans dépendance doit rester fermable — sinon un livrable qui bloque *tout*
passerait le test de blocage.

Toute évolution des tests E2E doit préserver ce type de contre-épreuve.

**Le cap E2E est du tout-ou-rien** : `_functional_e2e_failed()` se déclenche dès qu'**une seule**
étape du scénario échoue, et plafonne tout le run à 40 %. Un livrable correct qui rate la dernière
étape tombe au même niveau qu'un livrable qui ne répond pas. Depuis le 2026-09-22, une stack qui **ne démarre pas** est
traitée de même (cap `runtime_not_started`) : avant, elle échappait au cap et pouvait dépasser un
livrable qui démarre mais rate une étape.

**Règle des contrôles positifs.** Un test « doit être rejeté » ne prouve rien si l'API est cassée
ou injoignable : l'absence de données passe alors pour une rejection. Chaque sonde négative exige
donc une preuve positive :

- `alg=none` / signature étrangère : la même requête `tasks` doit **réussir** avec le vrai token ;
- mot de passe faible : une inscription normale doit avoir réussi ;
- dépendance inexistante / statut invalide : une **erreur GraphQL** doit être renvoyée. Les ids
  fantômes sont bien formés (ObjectId *et* UUID) : un simple échec de cast d'id ne vaut pas
  contrôle d'existence.

## Pièges de mesure déjà rencontrés

- **Jest** imprime `Test Suites:` avant `Tests:` : les compteurs se lisent sur la ligne `Tests:`,
  sinon on prend le nombre de fichiers pour le nombre de tests (faux malus « tests déclarés non
  exécutés »).
- **Makefile** : la cible de teardown est souvent `$(COMPOSE) down` avec `COMPOSE := docker compose`
  — le checker résout ces alias.
- **Regex statiques** : un signal (guard d'auth, healthcheck, fichier vide) doit reconnaître les
  formes idiomatiques (`requireUser`, `throw new UnauthenticatedError`, champ SDL `health: String!`,
  code écrit sur une ligne). Avant d'ajouter un motif, le confronter aux livrables présents.

## Où vivent les seuils

`auditor/scoring_config.py` : `TRACE_SCORING_CONFIG` (métriques déclarées par l'agent),
`TECHNICAL_STATS_SCORING_CONFIG` (métriques du code livré), `MODEL_PRICING` + `COST_USD_BANDS` +
`TOTAL_TOKENS_BANDS` (pilier Coût), plus les bandes et les caps. Rien dans `pyproject.toml` ou
l'outillage de lint n'influence le scoring — c'est un invariant, voir
[`../REGLES/lois.md`](../REGLES/lois.md).

`MODEL_PRICING` est une table **maintenue à la main**, avec sa date de dernière vérification
(`PRICING_UPDATED`) affichée dans le rapport. Elle se périme : un prix qui change côté fournisseur
sans être répercuté fausse le pilier Coût des runs suivants. La changer n'affecte **que les audits
à venir** — le coût est figé dans `meta.cost` du `cr_*.json` au moment de l'audit, et la KB le
relit tel quel.
