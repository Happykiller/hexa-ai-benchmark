# Hexa-AI Benchmark: Framework de Calibration d'Agents

Ce projet est un benchmark industriel conçu pour évaluer la capacité des agents IA à délivrer des solutions logicielles **opérationnelles**, **architecturalement robustes** et **professionnelles**. 

L'objectif est de dépasser le simple test de génération de code pour mesurer la viabilité d'un livrable complet dans un environnement de production.

---

## 🎯 Objectifs du Benchmark

Le benchmark évalue quatre piliers fondamentaux :
1.  **Opérationnalité (50%)** : Le code doit compiler, être testé et démarrer via Docker sans intervention humaine.
2.  **Rigueur Architecturale (25%)** : Respect strict des principes de l'**Architecture Hexagonale**.
3.  **Qualité Logicielle (15%)** : Typage TypeScript strict, absence de `any`, linter propre.
4.  **Discipline & Traçabilité (10%)** : Capacité de l'agent à mesurer sa propre consommation de contexte et à documenter ses phases.

---

## 🏗️ L'Architecture Cible (Le Défi)

Le projet imposé aux agents est une **Todo List Multi-Bases** complexe :
- **Core Domain** : Logique métier isolée (entités, use cases, ports).
- **Adapters** : Double implémentation persistante (**MongoDB** et **MySQL**).
- **Entrypoints** : API **GraphQL** avec résolveurs et validation.
- **Dependency Injection** : Utilisation impérative de **InversifyJS**.
- **Containerisation** : Orchestration via **Docker Compose**.
- **Business Logic Avancée** : Gestion de graphes de dépendances entre tâches (une tâche est bloquée si ses pré-requis ne sont pas terminés).

---

## 🔍 Le Système d'Audit (L'Auditeur)

L'auditeur est un moteur d'analyse Python qui exécute un cycle de validation complet :

### 1. Cycle de Vie Opérationnel
L'auditeur utilise le `Makefile` généré par l'agent pour valider le workflow :
- `make setup` : Installation des dépendances.
- `make lint` : Validation des standards de code.
- `make build` : Compilation TypeScript (Étape critique).
- `make test` : Exécution de la suite de tests unitaires/intégration.
- `make start` : Déploiement de l'infrastructure Docker.

### 2. Validation E2E & Métriques
Une fois le système démarré, l'auditeur exécute :
- **Scénario Fonctionnel** : Création de tâches liées, tentatives de fermeture illégales, et validation de la logique métier via requêtes GraphQL réelles.
- **Analyse de Structure** : Vérification par Regex/AST qu'aucun import interdit ne traverse les couches (ex: le Domaine n'importe rien des Adapters).
- **Audit d'Over-Engineering** : Détection des abstractions prématurées (Managers de Factories, etc.).
- **Calcul de Performance** : Benchmark de latence (P95) sur les endpoints.

---

## 📊 Système de Notation (Scoring)

Le score final est une accumulation de points positifs et négatifs :
- **Positifs** : Build, Tests, Architecture, Typage, E2E.
- **Malus (Over-engineering)** : Pénalités pour la complexité inutile.
- **Bonus (Proactivité)** : Points supplémentaires pour la validation d'environnement, les logs structurés, ou la pagination Relay.

**⚠️ Seuil Critique :** Un livrable qui ne compile pas ou qui échoue au scénario fonctionnel E2E voit sa note plafonnée à **40/100**, indépendamment de la qualité théorique du code.

---

## 🚀 Utilisation du Benchmark

1.  **Phase de Test** : Fournir le contenu de `prompts/evaluation_prompt.md` à l'agent.
2.  **Collecte** : Récupérer le livrable dans le dossier `livrables/`.
3.  **Audit** :
    ```bash
    # Installation
    python3 -m venv venv && source venv/bin/activate
    pip install -r auditor/requirements.txt

    # Lancement du benchmark
    python auditor/main.py analyze livrables/NOM_DU_DOSSIER
    ```
4.  **Résultat** : Consulter `audit_report.md` généré dans le dossier du livrable.
