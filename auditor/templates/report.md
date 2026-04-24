# Rapport d'Audit de Calibration (Exhaustif)
**Cible :** {{ audit_data.meta.target_path }}
**Date début :** {{ audit_data.meta.audit_started_at }}
**Date fin :** {{ audit_data.meta.audit_finished_at }}
**Score Final : {{ audit_data.summary.global_score }}/100**

---

## 📊 Tableau Récapitulatif
| Catégorie | Statut | Points | Détail |
|-----------|--------|--------|--------|
{%- for point in audit_data.points %}
| **{{ point.id }}. {{ point.label }}** | {{ point.status|md_cell }} | {{ point.score|md_cell }}{% if point.max_score > 0 %}/{{ point.max_score }}{% endif %} | max_data={{ point.max_data|md_cell }} |
{%- endfor %}
| **TOTAL** | **{{ audit_data.summary.admission_status }}** | **{{ audit_data.summary.global_score }}/100** | Score Final |

---

## 🧭 Pipeline d'audit (Phases > Étapes > Modules)
{%- for phase in audit_data.phases %}
### {{ phase.label }} ({{ phase.score }}{% if phase.max_score > 0 %}/{{ phase.max_score }}{% endif %}) - {{ phase.status }}
| Étape | Statut | Module | Indicateur | Data | Max Data |
|-------|--------|--------|------------|------|----------|
{%- for step in phase.steps %}
{%- for module in step.modules %}
| {{ step.label|md_cell }} | {{ step.status|md_cell }} | {{ module.label|md_cell }} | {{ module.indicator|md_cell }} | {{ module.data|md_cell }} | {{ module.max_data|md_cell }} |
{%- endfor %}
{%- endfor %}
{% endfor %}

---

## 🛠️ 1. Contrôles d'Opérationnalité (50%)
{%- set p1 = audit_data.points[0] %}
| Point de contrôle | Statut | Sortie / Erreur |
|-------------------|--------|-----------------|
| `make setup` | {{ p1.details.make_targets.setup.status|md_cell }} | {{ (p1.details.make_targets.setup.error or p1.details.make_targets.setup.output or "No errors")|md_cell }} |
| `make lint` | {{ p1.details.make_targets.lint.status|md_cell }} | {{ (p1.details.make_targets.lint.error or p1.details.make_targets.lint.output or "No errors")|md_cell }} |
| `make build` | {{ p1.details.make_targets.build.status|md_cell }} | {{ (p1.details.make_targets.build.error or p1.details.make_targets.build.output or "No errors")|md_cell }} |
| `make test` | {{ p1.details.make_targets.test.status|md_cell }} | {{ (p1.details.make_targets.test.error or p1.details.make_targets.test.output or "No errors")|md_cell }} |
| `make start` (Docker) | {{ p1.details.docker_start.status|md_cell }} | {{ (p1.details.docker_start.error or p1.details.docker_start.output or p1.details.docker_start.details or "Not run")|md_cell }} |

### Conteneurs exposés après `make start`
{% if p1.details.exposed_containers and p1.details.exposed_containers.status == "SUCCESS" and p1.details.exposed_containers.containers %}
| Conteneur | State | Status | Ports exposés |
|-----------|-------|--------|---------------|
{%- for c in p1.details.exposed_containers.containers %}
| {{ c.name|md_cell }} | {{ c.state|md_cell }} | {{ c.status|md_cell }} | {{ (c.ports or c.publishers)|md_cell }} |
{%- endfor %}
{% else %}
Inspection conteneurs: {{ (p1.details.exposed_containers.error or p1.details.exposed_containers.status or "Not run")|md_cell }}
{% endif %}

### Scénario Fonctionnel E2E (Business Rules)
{% if p1.details.e2e_results %}
| Étape de validation | Statut | Détail |
|---------------------|--------|--------|
{%- for step in p1.details.e2e_results %}
| {{ step.step|md_cell }} | {{ "SUCCESS" if step.success else "FAILED" }} | {{ (step.error or "Vérifié")|md_cell }} |
{%- endfor %}
{% else %}
⚠️ **Scénario E2E non exécuté** (Dépendances opérationnelles manquantes).
{% endif %}

---

## 🏛️ 2. Architecture Hexagonale (25%)
{%- set p2 = audit_data.points[1] %}
**Score : {{ p2.score }}/{{ p2.max_score }}**

### Liste exhaustive des points de contrôle
| Règle d'Isolation | Statut | Observations |
|-------------------|--------|--------------|
{%- for rule in p2.details.rules %}
| {{ rule.rule|md_cell }} | {{ rule.status|md_cell }} | {{ rule.violations_count|md_cell }} violations détectées |
{%- endfor %}

{% if p2.details.violations %}
#### Détail des violations
{%- for violation in p2.details.violations %}
- `{{ violation.file }}` : {{ violation.reason|md_cell }}
{%- endfor %}
{% endif %}

---

## 💎 3. Qualité & Typage (15%)
{%- set p3 = audit_data.points[2] %}
**Score : {{ p3.score }}/{{ p3.max_score }}**

### Liste exhaustive des points de contrôle
| Critère de Qualité | Statut | Détail |
|--------------------|--------|--------|
{%- for point in p3.details.points %}
| {{ point.name|md_cell }} | {{ point.status|md_cell }} | {{ point.detail|md_cell }} |
{%- endfor %}

---

## 📜 4. Traçabilité (10%)
{%- set p4 = audit_data.points[3] %}
**Score : {{ p4.score }}/{{ p4.max_score }}**

- **Fichier `audit_trace.json` :** {{ "Trouvé" if p4.details.status == "SUCCESS" else "Manquant ou invalide" }}
- **Phases identifiées :** {{ p4.details.phases_count|md_cell }}

{% if p4.details.data and p4.details.data.phases %}
### Détails issus de `audit_trace.json`
| Step | Start Time | End Time | Context Usage (%) |
|------|------------|----------|-------------------|
{%- for phase in p4.details.data.phases %}
| {{ phase.step|md_cell }} | {{ phase.start_time|md_cell }} | {{ phase.end_time|md_cell }} | {{ phase.context_usage_percent|md_cell }} |
{%- endfor %}
{% elif p4.details.error %}
- Erreur : {{ p4.details.error|md_cell }}
{% endif %}

---

## 🎁 5. Bonus & Initiatives Proactives
{%- set p5 = audit_data.points[4] %}
| Initiative | Statut | Points |
|------------|--------|--------|
{%- for bonus in p5.details.all_bonuses %}
| {{ bonus.reason|md_cell }} | {{ bonus.status|md_cell }} | {{ ("+" ~ bonus.points) if bonus.status == "SUCCESS" else "+0" }} |
{%- endfor %}

### Malus (Dette technique / Over-engineering)
{% if p5.details.maluses %}
| Problème | Gravité | Impact |
|----------|---------|--------|
{%- for malus in p5.details.maluses %}
| {{ malus.reason|md_cell }} | ÉLEVÉE | {{ malus.points|md_cell }} pts |
{%- endfor %}
{% else %}
Aucun malus détecté.
{% endif %}

---

## 📈 Statistiques Techniques
- **Lignes de code (TS) :** {{ stats.total_lines|md_cell }}
- **Nombre de fichiers TS :** {{ stats.total_ts_files|md_cell }}
- **Nombre total de fichiers :** {{ stats.total_files|md_cell }}
- **Volume total :** {{ stats.total_size_kb|md_cell }} KB
- **Performance (Latence Moyenne) :** {{ p1.details.performance.avg_latency_ms|round(2) if p1.details.performance.avg_latency_ms > 0 else "N/A" }} ms

---
*Fin du rapport d'audit exhaustif.*
