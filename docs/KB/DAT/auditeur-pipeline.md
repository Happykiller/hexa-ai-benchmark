---
titre: Pipeline d'audit — phases, checkers et parti pris
type: dat
statut: actif
maj: 2026-07-27
---

# Pipeline d'audit

`auditor/main.py` est l'orchestrateur. Il alimente une structure `audit_db` imbriquée
(phases → étapes → indicateurs), finalise en calculant les scores pondérés
(`_finalize_audit_db()`), puis rend `auditor/templates/report.md` via Jinja2.

## Les trois phases

1. **Statique** — lecture des sources du livrable.
2. **Dynamique** — exécution réelle : cibles `make`, Docker, E2E, benchmark.
3. **Traçabilité** — lecture de l'`audit_trace.json` fourni par l'agent.

L'ordre n'est pas arbitraire : la phase statique est peu coûteuse et sert de filtre, la phase
dynamique prend des minutes et peut échouer pour des raisons d'environnement (voir
[environnements.md](environnements.md)).

## Checkers statiques — `modules/static_analysis.py`

| Checker | Ce qu'il mesure | Point de vigilance |
|---|---|---|
| `HexagonalComplianceChecker` | Isolation des couches (Core n'importe pas d'ailleurs) | Strippe les commentaires par regex avant de scanner les imports — sinon un import commenté compterait |
| `CodeQualityChecker` | Occurrences de `any` TypeScript | Score inverse : 100 − count×2 |
| `ProjectStatsAnalyzer` | Fichiers, TS/TSX, LOC, tests, taille | Alimente `TECHNICAL_STATS_SCORING_CONFIG` |
| `CodeSmellAnalyzer` | Bonus (erreurs custom, validation d'env, healthcheck, pagination Relay, log structuré) et malus (AbstractFactory, fragmentation extrême >30 % de fichiers <10 lignes) | Le malus de fragmentation existe pour punir le découpage cosmétique |
| `ReadmeChecker` | Sections requises **avec contenu réel** | Un heading vide ne rapporte rien |

`modules/supply_chain.py` ajoute `DevExChecker` (tsconfig `strict` réellement activé, ESLint, CI,
`.gitignore` sain), `SecretsScanner` et `NpmAuditChecker` — ces deux derniers en malus.

## Checkers dynamiques — `modules/dynamic_analysis.py`

| Checker | Ce qu'il fait |
|---|---|
| `MakefileRunner` | Exécute une cible make (timeout 5 min), capture stdout/stderr et code retour |
| `DockerOrchestrator` | Démarre la stack, sonde la santé (max 30 essais × 2 s), lit l'état des conteneurs |
| `E2EFunctionalTester` | Scénario GraphQL de blocage par dépendances |
| `AuthTester` | Auth + sécurité réelle : `alg:none` rejeté, signature étrangère rejetée, isolation inter-utilisateurs, code `UNAUTHENTICATED` exact, mot de passe faible refusé — JWT forgés avec la stdlib, sans dépendance ajoutée |
| `PerformanceBenchmarker` | 50 requêtes GraphQL : latence moyenne, P95, taux d'erreur |

## Parti pris : orchestrateur challenge-agnostique

`auditor/challenges.py` isole tout ce qui est spécifique au défi Todo (endpoint GraphQL, noms et
poids des étapes E2E, noms de couches) dans un `ChallengeProfile`. `TODO_STATIC_CHECKERS` est un
**registre déclaratif** : chaque checker porte son mapper `emit`, qui réutilise `_append_indicator`.

Conséquence pratique, et c'est le point à retenir : **ajouter un contrôle statique = une entrée de
registre, sans toucher à `main.py`**. Un changement qui modifie `main.py` pour ajouter un checker
rate l'intention de l'architecture.

## Anti-triche

Plusieurs contrôles existent uniquement pour empêcher un agent de gagner des points sans
implémenter la logique. Le plus explicite : dans l'E2E de dépendances, fermer « B alors que A est
ouverte » doit échouer avec un message contenant `depend|blocked|prerequisite|precondition`,
**et** une tâche sans dépendance doit rester fermable — sinon un livrable qui bloque *tout*
passerait le test de blocage.

Toute évolution des tests E2E doit préserver ce type de contre-épreuve.

## Où vivent les seuils

`auditor/scoring_config.py` : `TRACE_SCORING_CONFIG` (métriques déclarées par l'agent) et
`TECHNICAL_STATS_SCORING_CONFIG` (métriques du code livré), plus les bandes et les caps. Rien dans
`pyproject.toml` ou l'outillage de lint n'influence le scoring — c'est un invariant, voir
[`../REGLES/lois.md`](../REGLES/lois.md).
