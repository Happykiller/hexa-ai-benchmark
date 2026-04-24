# Challenge Technique : Application TODO Hexagonale Multi-Bases

## 1. Contexte et Objectif
Votre mission est de concevoir une application de gestion de tâches (Todo List) professionnelle en utilisant TypeScript, en respectant une **Architecture Hexagonale** stricte. L'application doit exposer une API GraphQL et supporter deux types de bases de données (MongoDB et MySQL) de manière interchangeable via l'injection de dépendances.

## 2. Contraintes Techniques Obligatoires
- **Autonomie d'exécution (CRITIQUE) :** La demande doit être traitée **en toute autonomie**, sans tenir compte de ce qui est déjà présent dans `livrables/`, `cr_audits/` et `auditor/`. Aucun artefact existant dans ces dossiers ne doit être utilisé comme base, référence, dépendance ou justification pour limiter le traitement de la demande.
- **Makefile (CRITIQUE) :** Vous devez fournir un fichier `Makefile` à la racine contenant les cibles `setup`, `lint`, `build`, `test`, et `start`. Les cibles `make` doivent piloter l'exécution du projet, y compris l'orchestration Docker/Compose (en particulier `make start`). Un livrable qui ne compile pas ou dont les cibles `make` échouent recevra un score éliminatoire.
- **Langage :** TypeScript (mode strict).
- **Architecture :** Hexagonale (Core/Domain, Use Cases, Ports, Adapters, Entrypoints).
- **API :** GraphQL (Schema-first ou Code-first).
- **DI :** InversifyJS pour la gestion des singletons et l'injection.
- **Bases de données :** MongoDB ET MySQL (implémentation via Repository Pattern).
- **Conteneurisation (CRITIQUE) :** Docker (un `docker-compose.yml` pour l'API, Mongo et MySQL). La conteneurisation fait partie intégrante d'une implémentation fiable et résiliente.
- **Tests :** BDD avec Gherkin pour les règles métier, Jest pour les tests unitaires et d'intégration.
- **Linter/Style :** ESLint et Prettier configurés.

## 3. Organisation du Livrable
Vous devez générer tout votre code dans un sous-dossier nommé selon le format suivant :
`livrables/YYYYMMDD_HHMM_[NOM_DU_MODELE]_[VOTRE_TEMPERATURE]/`

## 4. Traçabilité (Audit Trace)
Vous **devez** maintenir à la racine de votre dossier de livrable un fichier `audit_trace.json`.
Ce fichier doit être mis à jour à chaque phase avec les informations suivantes :
```json
{
  "phases": [
    {
      "step": 1,
      "start_time": "ISO_DATETIME",
      "end_time": "ISO_DATETIME",
      "context_usage_percent": 0
    }
  ]
}
```

## 5. Déroulement du Challenge (3 Phases)

### Phase 1 : Construction Massive (La Fondation)
1. Mettez en place l'architecture hexagonale et l'injection de dépendances avec InversifyJS.
2. Implémentez le CRUD de base pour les tâches (ID, Titre, Description, Statut, Date de création).
3. Configurez Docker pour monter l'API et les deux bases de données.
4. L'application doit pouvoir démarrer sur Mongo ou MySQL via une variable d'environnement `DB_TYPE`.
5. Fournissez une suite de tests validant le CRUD de base.
6. `make start` doit effectivement lancer la stack conteneurisée (API + bases), avec des services observables via les commandes Docker standard.

### Phase 2 : Transformation Aboutie (Évolution Complexe)
1. **Règles de Dépendance :** Une tâche peut dépendre d'autres tâches. Une tâche ne peut être marquée comme "terminée" QUE SI toutes ses dépendances sont elles-mêmes "terminées".
2. **Authentification :** Remplacez le mock d'utilisateur par un système de validation JWT (même si les utilisateurs sont en dur en base pour l'instant).
3. Les règles Gherkin doivent couvrir le cas des dépendances.

### Phase 3 : Micro-actions (Optimisation & Fine-tuning)
1. **Performance :** Implémentez un `DataLoader` dans vos résolveurs GraphQL pour éviter le problème de requêtes N+1 lors de la récupération des dépendances d'une liste de tâches.
2. **Audit Trail :** Chaque modification de statut d'une tâche doit être logguée dans une table/collection `AuditLog` avec le timestamp et l'ID de l'utilisateur.

## 6. Critères d'Évaluation (Cachés)
Votre code sera audité par un script Python qui vérifiera de manière séquentielle :
1. **L'Opérationnalité (50%) :** Le build doit passer, les tests doivent réussir, et le système doit être déployable via Docker.
   Séquence d'audit opérationnelle attendue :
   - exécution de `make start`,
   - contrôle des conteneurs exposés/actifs via Docker,
   - puis lancement de la suite de tests fonctionnels (E2E) via HTTP pour valider le Use Case des dépendances.
2. **L'Architecture & Qualité (40%) :** Respect strict de l'architecture hexagonale et qualité du typage.
3. **La Traçabilité (10%) :** Validité de l'historique dans `audit_trace.json`.
4. **Bonus/Malus :** Récompense pour les initiatives proactives (logs, validation env) et pénalités pour l'over-engineering (abstractions inutiles).

**Note Importante :** Un projet qui ne build pas ou qui échoue aux tests fonctionnels sera capé à un score maximum de 40/100, quel que soit le soin apporté au code.
