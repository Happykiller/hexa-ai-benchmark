# Spécifications Techniques : API Todo Hexagonale Multi-Base

**Version du prompt : `2606082200`**

---

> ### Mode d'exécution — Session entièrement autonome
>
> Ce cahier des charges est **complet et auto-suffisant**. Vous devez le réaliser sans interaction humaine :
>
> - **Planifiez en amont** : avant d'écrire la première ligne de code, établissez votre séquence de tâches, vos choix d'implémentation et votre découpage en phases. Ce plan ne doit être soumis à personne.
> - **Décidez seul** : ne posez aucune question, ne demandez aucune confirmation ni validation en cours de session. Si un point est ambigu, tranchez en faveur de l'option la plus raisonnée et continuez.
> - **Livrez complet** : l'objectif est un livrable fonctionnel, testé et documenté à l'issue d'une **seule session continue**.

---

> ### Discipline de planification obligatoire
>
> Avant toute modification de fichiers, établissez un plan d'exécution interne en 3 à 6 étapes. Ce plan doit couvrir au minimum :
>
> - l'ordre de construction du livrable ;
> - la stratégie Docker/Makefile compatible avec l'auditeur ;
> - les choix d'architecture hexagonale ;
> - la stratégie de tests et de validation finale.
>
> Ce plan est un outil de travail interne : ne le soumettez pas à validation, ne demandez aucune confirmation humaine, et ne laissez jamais la planification remplacer la livraison d'un code fonctionnel.

---

## 1. Objectif
Développer un service de gestion de tâches (Todo List) hautement qualitatif, utilisant une **Architecture Hexagonale** et supportant dynamiquement deux moteurs de stockage (**MongoDB** et **MySQL**).

## 2. Contrat d'Interface Mandatory
Les interfaces suivantes sont contractuelles. Tout écart rompt la compatibilité avec les outils de vérification automatisée du projet.

### 2.1 Pilotage via Makefile
L'intégralité du cycle de vie du projet doit être pilotable via un `Makefile` à la racine du livrable. **Toutes les commandes (sauf setup) doivent cibler l'environnement Docker.**

| Commande | Action attendue |
| :--- | :--- |
| `make setup` | Installe les dépendances nécessaires sur l'hôte (ex: `npm install`). |
| `make start` | Démarre la stack complète (`docker-compose up -d`). L'API doit être disponible sur le port 4000 après cette commande. |
| `make lint` | Exécute les vérifications de style et de typage à l'intérieur du conteneur. |
| `make build` | Compile le projet TypeScript à l'intérieur du conteneur. |
| `make test` | Lance les tests unitaires et d'intégration à l'intérieur du conteneur **avec rapport de couverture** (`--coverage`). |
| `make down` | **Arrête et supprime** les conteneurs et réseaux de la stack (`docker compose down`). Doit garantir un environnement propre après le travail. |

**Ordre d'exécution par l'auditeur :** les cibles sont appelées dans cet ordre strict : `make setup`, `make lint`, `make build`, `make test`, puis `make start` ; l'auditeur termine en supprimant les conteneurs qu'il a lancés. Le livrable **doit** fournir `make down` (cible de teardown vérifiée).

Conséquence : `make lint`, `make build` et `make test` doivent être exécutables avant que `make start` ait démarré la stack. Ces cibles ne doivent donc pas dépendre d'un conteneur déjà actif via `docker compose exec`. Utilisez `docker compose run --rm api ...`, `docker build`, ou une commande Docker équivalente capable de fonctionner depuis un état froid.

### 2.2 Spécifications API GraphQL
L'API doit être exposée sur `http://localhost:4000/graphql`.

**Schéma minimal requis :**
```graphql
type Task {
  id: ID!
  title: String!
  description: String
  status: String! # Valeurs : "OPEN", "COMPLETED"
  dependsOn: [Task!]
}

type Query {
  tasks: [Task!]!
}

type Mutation {
  createTask(input: CreateTaskInput!): Task!
  updateTaskStatus(id: ID!, status: String!): Task!
}

input CreateTaskInput {
  title: String!
  description: String
  dependsOn: [ID!] # IDs des tâches dont celle-ci dépend
}
```

**Règles de validation (E2E) :**
- **Statuts :** Une tâche créée est par défaut `OPEN`.
- **Règle de dépendance :** La mutation `updateTaskStatus(status: "COMPLETED")` doit échouer tant qu'**au moins une** des tâches présentes dans `dependsOn` n'est pas elle-même au statut `COMPLETED` (toutes les dépendances sont requises, à n'importe quelle profondeur de chaîne).
- **Statut invalide :** `updateTaskStatus` doit **rejeter** toute valeur de statut autre que `OPEN` ou `COMPLETED` (pas de statut arbitraire accepté).
- **Dépendance inexistante :** `createTask` doit **rejeter** un `dependsOn` qui référence un identifiant de tâche inexistant.
- **Format d'erreur :** En cas d'échec de la règle de dépendance, l'erreur retournée dans la réponse GraphQL doit contenir au moins un de ces mots-clés : `blocked`, `depend`, `prerequisite`, ou `precondition`.

### 2.3 Conteneurisation et Double Persistance

L'API utilise **simultanément** les deux bases de données, chacune affectée à un domaine métier distinct :

| Base | Entités stockées | Technologie recommandée |
| :--- | :--- | :--- |
| **MySQL** | `User` (id, email, password hash) | TypeORM ou Sequelize |
| **MongoDB** | `Task` (id, title, status, dependsOn, userId) | Mongoose |

**Docker Compose :** Doit orchestrer trois services : `api`, `mongodb`, et `mysql`. Les deux connexions sont initialisées au démarrage — **aucun commutateur** : les deux adaptateurs sont actifs en permanence.

**Ports hôte (obligatoires).** Pour éviter toute collision avec des bases déjà présentes sur la machine d'audit, publiez les services sur ces ports hôte **exacts** (le port conteneur reste standard) :

| Service | Mapping `ports:` (hôte:conteneur) |
| :--- | :--- |
| `api` | `4000:4000` |
| `mongodb` | `47017:27017` |
| `mysql` | `43306:3306` |

L'API communique avec les bases via les **noms de service compose** (`mongodb:27017`, `mysql:3306`) sur le réseau interne — **jamais via `localhost`**. Les ports hôte ci-dessus ne servent qu'à l'inspection externe et sont vérifiés automatiquement.

**Variables d'environnement attendues :**
- `MONGO_URI` (ex : `mongodb://mongodb:27017/tasks`)
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD`

**Note :** Utiliser le format Docker Compose v2+ sans le champ `version:` de haut niveau (obsolète).

### 2.4 Authentification & Sécurité (JWT)

L'API doit sécuriser ses opérations via **JSON Web Tokens (JWT)**. Les données utilisateurs (`User`, credentials) sont persistées dans **MySQL** (voir §2.3).

**Nouveaux types GraphQL :**
```graphql
type User {
  id: ID!
  email: String!
}

type AuthPayload {
  token: String!
  user: User!
}
```

**Nouvelles opérations :**
```graphql
type Query {
  me: User!                        # Requiert authentification
  tasks: [Task!]!                  # Retourne uniquement les tâches de l'utilisateur connecté
}

type Mutation {
  register(email: String!, password: String!): AuthPayload!
  login(email: String!, password: String!): AuthPayload!
  createTask(input: CreateTaskInput!): Task!        # Requiert authentification
  updateTaskStatus(id: ID!, status: String!): Task! # Requiert authentification
}
```

**Règles de protection :**
- Les mutations `createTask` et `updateTaskStatus` ainsi que les queries `me` et `tasks` nécessitent un token valide transmis dans le header HTTP : `Authorization: Bearer <token>`.
- Une requête sans token ou avec un token invalide/expiré doit retourner une erreur GraphQL avec `extensions.code = "UNAUTHENTICATED"`.
- Les tâches sont cloisonnées par utilisateur : `tasks` ne retourne que les tâches appartenant à l'utilisateur authentifié.

**Contraintes de sécurité :**
- **Longueur minimale du mot de passe : 8 caractères.** Toute tentative de `register` avec un mot de passe plus court doit être rejetée par une erreur GraphQL, sans création de compte.
- Mot de passe haché en base (bcrypt ou argon2, coût ≥ 10).
- Secret JWT isolé dans la variable d'environnement `JWT_SECRET`.
- Durée d'expiration configurable via `JWT_EXPIRES_IN` (défaut : `7d`).
- **Validation stricte du token** : un token non signé (`alg: none`) ou signé avec un secret étranger doit être rejeté (`UNAUTHENTICATED`). N'acceptez jamais d'algorithme arbitraire côté serveur — fixez explicitement l'algorithme de vérification.

## 3. Exigences Architecturales

### 3.1 Responsabilité des Couches

Chaque couche a **une seule responsabilité** et des **types qui lui sont propres** — aucun DTO, modèle ou entité n'est partagé entre couches :

| Couche | Responsabilité unique | Technologies |
| :--- | :--- | :--- |
| `core/` | Entités métier, ports (interfaces), use cases | TypeScript pur, aucune lib |
| `adapters/` | Implémentation des ports (repositories) | Mongoose, TypeORM/Sequelize |
| `infrastructure/` | Config, connexions DB, conteneur IoC | InversifyJS, drivers DB |
| `entrypoints/` | Résolveurs GraphQL, serveur HTTP | Apollo, Express |

`core/` ne dépend d'aucune autre couche. `adapters/` et `infrastructure/` ne dépendent pas de `entrypoints/`.

### 3.2 Injection de Dépendances (Use Cases)

Les use cases (`core/`) contiennent **uniquement de la logique métier pure**. Toutes les dépendances externes sont **injectées dans le constructeur** via InversifyJS — aucune instanciation directe de classe concrète dans `core/` :

```typescript
// ✅ Correct — pur, testable, découplé
@injectable()
export class CreateTaskUseCase {
  constructor(
    @inject(TYPES.ITaskRepository) private taskRepo: ITaskRepository,
    @inject(TYPES.IUserRepository) private userRepo: IUserRepository,
  ) {}
  async execute(dto: CreateTaskDto): Promise<Task> { /* logique seule */ }
}

// ❌ Interdit dans core/ — couplage direct, non testable
class CreateTaskUseCase {
  private repo = new TaskMongoRepository(); // instanciation directe interdite
}
```

Cette contrainte garantit la testabilité unitaire sans infrastructure (mock des interfaces).

### 3.3 Double Persistance

InversifyJS wire deux familles de repositories distinctes :
- `TaskMongoRepository` → Mongoose → **MongoDB**
- `UserMysqlRepository` → TypeORM/Sequelize → **MySQL**

Les interfaces `ITaskRepository` et `IUserRepository` définies dans `core/` sont identiques. Seules les implémentations dans `adapters/` diffèrent.

### 3.4 Qualité de Code
- TypeScript en mode `strict: true`. Toute utilisation du type `any` est détectée et pénalisée.
- Utilisation obligatoire d'**InversifyJS** pour l'injection des repositories et des services.

### 3.5 Outillage, Qualité statique & Intégration Continue

Les éléments suivants sont **attendus à la racine du livrable** et vérifiés automatiquement par l'auditeur :

- **Configuration ESLint** : un fichier de configuration ESLint (`.eslintrc*` ou `eslint.config.*`) présent à la racine et utilisé par la cible `make lint`.
- **Pipeline d'intégration continue** : au moins un workflow GitHub Actions dans `.github/workflows/*.yml` enchaînant au minimum `lint`, `build` et `test`.
- **`.gitignore`** : présent à la racine et couvrant au minimum `node_modules/` et les fichiers `.env`.

## 4. Organisation et Traçabilité

### 4.1 Structure du Livrable

Le livrable **doit respecter exactement** l'arborescence suivante. Les noms de dossiers sont imposés.

```
./YYYYMMDD_HHMM_[MODEL]_[TEMP]/
├── audit_trace.json         # Traçabilité de session (voir §4.3)
├── Makefile                 # Cibles : setup / lint / build / test / start / down
├── docker-compose.yml       # Services : api, mongodb, mysql (sans champ version:)
├── package.json
├── tsconfig.json            # strict: true obligatoire
├── .eslintrc.json           # Configuration ESLint (ou eslint.config.*)
├── .gitignore               # Couvre au minimum node_modules/ et .env
├── .github/
│   └── workflows/
│       └── ci.yml           # Pipeline CI : lint + build + test
├── src/
│   ├── core/                # Domaine pur — ports, entités, use cases
│   ├── adapters/            # Implémentations concrètes des ports (repositories)
│   ├── infrastructure/      # Config, connexions DB, conteneur IoC (InversifyJS)
│   └── entrypoints/         # Serveur HTTP/Apollo, résolveurs GraphQL
└── README.md
```

> ⚠️ Les noms `core/`, `adapters/`, `infrastructure/`, `entrypoints/` sont **obligatoires** et non renommables. Les outils de vérification structurelle s'appuient sur ces noms exacts.

### 4.2 README.md

Le `README.md` doit contenir **explicitement** les quatre sections suivantes :

| Section | Contenu attendu |
| :--- | :--- |
| **Architecture** | Description de la structure hexagonale et du rôle de chaque couche. |
| **Installation** | Instructions de démarrage (`make setup`, `make start`). |
| **API GraphQL** | Documentation des queries, mutations et types. |
| **Docker** | Explication des services et des variables d'environnement. |

### 4.3 audit_trace.json

Fichier de suivi **obligatoire** à la racine du livrable. Il mesure l'efficacité de la session de l'agent et doit être produit avec des valeurs réelles (pas des zéros). L'agent doit également indiquer un maximum d'informations sur son contexte d'exécution dans un objet `meta`.

**Description de chaque champ :**

| Champ | Type | Définition |
| :--- | :--- | :--- |
| `meta.prompt_version` | `string` | Version exacte du présent prompt, à recopier telle quelle : `"2606082200"` |
| `meta.model` | `string` | Le nom exact du modèle d'IA utilisé (ex: "gpt-4o", "claude-3-7-sonnet", "gemini-1.5-pro") |
| `meta.temperature` | `number` | La température configurée pour la génération |
| `meta.effort` | `string` | Le niveau d'effort ou de raisonnement (reasoning effort) configuré |
| `meta.config` | `object` | Toute autre configuration pertinente de l'agent (top_p, max_tokens, system prompt, etc.) |
| `summary.total_turns` | `number` | Nombre total d'échanges User ↔ Agent sur l'ensemble de la session |
| `summary.total_tool_calls` | `number` | Nombre total d'appels d'outils (shell, lecture/écriture fichiers, recherche…) |
| `summary.total_wall_time_seconds` | `number` | Durée totale réelle de la session en secondes (horloge murale, pas CPU) |
| `summary.total_input_tokens` | `number` | **Total des tokens d'entrée (prompt) sur la session, cache inclus.** Sert au calcul du coût (pilier scoré). |
| `summary.total_output_tokens` | `number` | **Total des tokens de sortie (génération) sur la session.** Sert au calcul du coût. |
| `summary.total_cached_input_tokens` | `number` | *(optionnel)* Parmi `total_input_tokens`, le **sous-ensemble** servi depuis le cache (facturé moins cher). |
| `phases[].phase` | `number` | Numéro de la phase (1, 2, 3) correspondant aux phases de développement §5 |
| `phases[].label` | `string` | Nom court de la phase |
| `phases[].start_time` | `string` | Début de la phase — ISO-8601 UTC, ex : `"2024-06-01T09:00:00Z"` |
| `phases[].end_time` | `string` | Fin de la phase — même format |
| `phases[].turns_in_phase` | `number` | Échanges User ↔ Agent pendant cette seule phase |
| `phases[].tool_calls_in_phase` | `number` | Appels d'outils pendant cette seule phase |

> `total_wall_time_seconds` peut être lu depuis le chronomètre de la plateforme **ou** calculé comme la somme des durées de phases (`end_time − start_time`). Les deux méthodes sont acceptées.

> **Coût (pilier scoré) :** le coût en dollars est un **pilier de notation à part entière**. L'auditeur le calcule lui-même à partir de `total_input_tokens` / `total_output_tokens` et d'une table de prix par modèle — l'agent rapporte donc les **tokens**, pas le prix. Reportez des compteurs réels (la plupart des plateformes les exposent : Claude `/cost`, usage API). **Des tokens absents ⇒ 0 sur le pilier Coût.**

**Exemple complet avec valeurs réalistes :**

```json
{
  "meta": {
    "prompt_version": "2606082200",
    "model": "claude-3-7-sonnet-20250219",
    "temperature": 0.2,
    "effort": "high",
    "config": {
      "top_p": 0.9,
      "max_tokens": 8192
    }
  },
  "summary": {
    "total_turns": 42,
    "total_tool_calls": 187,
    "total_wall_time_seconds": 3240,
    "total_input_tokens": 480000,
    "total_output_tokens": 95000,
    "total_cached_input_tokens": 120000
  },
  "phases": [
    {
      "phase": 1,
      "label": "Setup & Architecture Hexagonale",
      "start_time": "2024-06-01T09:00:00Z",
      "end_time": "2024-06-01T09:45:00Z",
      "turns_in_phase": 14,
      "tool_calls_in_phase": 62
    },
    {
      "phase": 2,
      "label": "Logique métier & Authentification JWT",
      "start_time": "2024-06-01T09:45:00Z",
      "end_time": "2024-06-01T10:25:00Z",
      "turns_in_phase": 18,
      "tool_calls_in_phase": 79
    },
    {
      "phase": 3,
      "label": "Optimisation & Finitions",
      "start_time": "2024-06-01T10:25:00Z",
      "end_time": "2024-06-01T10:54:00Z",
      "turns_in_phase": 10,
      "tool_calls_in_phase": 46
    }
  ]
}
```

> **Conseil :** certaines plateformes exposent les métriques de session nativement (Claude : `/status`, `tokens` ; Gemini : paramètres de session). Sinon, incrémenter les compteurs manuellement à chaque changement de phase et noter les timestamps ISO.

### 4.4 Couverture de Tests

Les fichiers de tests doivent utiliser la convention Jest (`.test.ts` ou `.spec.ts`, ou placés dans un dossier `tests/` ou `__tests__/`). Viser un minimum de **15 fichiers de tests** couvrant les use cases du domaine et les adaptateurs.

La configuration Jest **doit activer le rapport de couverture** (`--coverage` ou `collectCoverage: true` dans `jest.config.js`) **et émettre le reporter `json-summary`** (`coverageReporters: ["text", "json-summary"]`), qui produit `coverage/coverage-summary.json`. L'auditeur en dérive la couverture **par couche**.

Cibles de couverture de lignes — le domaine est testé plus strictement que les bords :

| Couche | Cible |
| :--- | :--- |
| `core/` | ≥ 85 % |
| `adapters/` | ≥ 60 % |
| `entrypoints/` | ≥ 40 % |

La couverture globale reste mesurée (cible **≥ 80 %**) à partir de la sortie de `make test`. Si `coverage-summary.json` est absent, la couverture par couche est simplement non comptée (sans pénalité).

## 5. Phases de Développement
- **Phase 1 :** Setup, Architecture Hexagonale, CRUD simple, Docker Compose et Makefile.
- **Phase 2 :** Logique des dépendances, Tests BDD (Gherkin), Authentification JWT.
- **Phase 3 :** Optimisation GraphQL (DataLoader), Logs d'audit (AuditLog) et finitions.

**Attention :** L'absence d'une cible `make` fonctionnelle ou d'un champ requis dans l'API GraphQL est éliminatoire pour la certification du livrable.

## 6. Bonnes Pratiques Attendues

Les initiatives suivantes ne sont pas bloquantes mais caractérisent un livrable de qualité professionnelle :

- **Gestion d'erreurs centralisée** : définir des classes d'erreurs métier héritant de `Error` (ex : `class TaskNotFoundError extends Error {}`).
- **Validation des variables d'environnement** : utiliser `zod` ou `envalid` pour valider `DB_TYPE`, `JWT_SECRET`, `PORT`, etc. au démarrage — l'application doit échouer explicitement si une variable obligatoire est absente.
- **Endpoint de santé** : exposer une query GraphQL `health` (ou `ping`) retournant le statut de disponibilité de l'API.
- **Logger structuré** : intégrer `winston` ou `pino` à la place de `console.log` pour des logs en format JSON exploitables en production.
- **Pagination Relay** (optionnel avancé) : pour la query `tasks`, implémenter la pagination Cursor-based avec `PageInfo`, `edges { node { ... } }` et `cursor`.
