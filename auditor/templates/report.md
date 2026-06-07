# Rapport d'Audit par Indicateurs
**Cible :** {{ audit_data.meta.target_path }}
**Date début :** {{ audit_data.meta.audit_started_at }}
**Date fin :** {{ audit_data.meta.audit_finished_at }}
**Modèle de score :** {{ audit_data.meta.scoring_model }}

---

## Résumé global
| Mesure | Valeur |
|--------|--------|
| Points positifs gagnés | {{ audit_data.summary.positive_points_earned|md_cell }} |
| Points positifs possibles | {{ audit_data.summary.positive_points_possible|md_cell }} |
| Malus cumulés | {{ audit_data.summary.negative_points|md_cell }} |
| Score brut (Net) | {{ audit_data.summary.raw_total_score|md_cell }} |
| Score normalisé de base | {{ audit_data.summary.normalized_base_score|md_cell }}/{{ audit_data.summary.normalized_base_weight_total|md_cell }} |
| Ajustement bonus/malus appliqué | {{ audit_data.summary.bonus_malus_adjustment.capped_adjustment|md_cell }} |
| Pourcentage brut du score net | {{ audit_data.summary.raw_percentage_net|md_cell }}% |
| Pourcentage final du score net | {{ audit_data.summary.percentage_net|md_cell }}% |
| Nombre total d'indicateurs | {{ audit_data.summary.indicators_count|md_cell }} |

### Score par pilier
| Pilier | Score | Poids | Ratio brut |
|--------|-------|-------|------------|
{%- for bucket_name, bucket in audit_data.summary.bucket_scores.items() %}
| {{ bucket.label|md_cell }} | {{ bucket.normalized_score|md_cell }} | {{ bucket.weight|md_cell }} | {{ bucket.ratio|md_cell }} |
{%- endfor %}

{% if audit_data.summary.score_caps %}
### Caps éliminatoires
| Cap | Maximum | Raison |
|-----|---------|--------|
{%- for cap in audit_data.summary.score_caps %}
| {{ cap.id|md_cell }} | {{ cap.max_percentage|md_cell }}% | {{ cap.reason|md_cell }} |
{%- endfor %}
{% endif %}

---

## Synthèse par phase
| Phase | Points positifs gagnés | Points positifs possibles | Malus | Score brut |
|-------|------------------------|---------------------------|-------|------------|
{%- for phase in audit_data.phases %}
| {{ phase.code|md_cell }}. {{ phase.label|md_cell }} | {{ phase.positive_points_earned|md_cell }} | {{ phase.positive_points_possible|md_cell }} | {{ phase.negative_points|md_cell }} | {{ phase.raw_total|md_cell }} |
{%- endfor %}

---

## Revue détaillée des indicateurs par phase
{%- for phase in audit_data.phases %}
### Phase {{ phase.code }}. {{ phase.label }} (Score: {{ phase.positive_points_earned }}/{{ phase.positive_points_possible }})

{%- for step in phase.steps %}
#### Étape {{ step.code }}. {{ step.label }}
| Code | Indicateur | Valeur mesurée | Score obtenu | Score max | Remarques |
|------|------------|----------------|--------------|-----------|-----------|
{%- for indicator in step.indicators %}
| {{ indicator.code|md_cell }} | {{ indicator.name|md_cell }} | {{ indicator.measured_value|md_cell }} | {{ indicator.score|md_cell }} | {{ indicator.max_score|md_cell }} | {{ indicator.remarks|md_cell }} |
{%- endfor %}
{%- endfor %}

{% endfor %}
---

## Détails factuels
### Cibles make
| Cible | Résultat | Traces (stdout / stderr) |
|-------|----------|----------|
{%- for target_name, result in audit_data.artifacts.make_targets.items() %}
| {{ target_name|md_cell }} | {{ result.status|md_cell }} | {{ (result.output ~ "<br>---<br>" ~ (result.error or ""))|md_cell }} |
{%- endfor %}

### Infrastructure Docker
| Etape | Résultat | Traces |
|-------|----------|--------|
| make start | {{ audit_data.artifacts.docker_start.status|md_cell }} | {{ (audit_data.artifacts.docker_start.output ~ "<br>---<br>" ~ (audit_data.artifacts.docker_start.error or audit_data.artifacts.docker_start.stderr or ""))|md_cell }} |

### Conteneurs exposés
{% if audit_data.artifacts.exposed_containers.status == "OK" and audit_data.artifacts.exposed_containers.containers %}
| Conteneur | State | Status | Ports exposés |
|-----------|-------|--------|---------------|
{%- for container in audit_data.artifacts.exposed_containers.containers %}
| {{ container.name|md_cell }} | {{ container.state|md_cell }} | {{ container.status|md_cell }} | {{ (container.ports or container.publishers)|md_cell }} |
{%- endfor %}
{% else %}
Inspection conteneurs: {{ (audit_data.artifacts.exposed_containers.error or audit_data.artifacts.exposed_containers.status)|md_cell }}
{% endif %}

### Résultats E2E
{% if audit_data.artifacts.e2e_results %}
| Étape | Succès | Message |
|-------|--------|---------|
{%- for step in audit_data.artifacts.e2e_results %}
| {{ step.step|md_cell }} | {{ step.success|md_cell }} | {{ (step.error or "validated")|md_cell }} |
{%- endfor %}
{% else %}
Scénario E2E non exécuté.
{% endif %}

### Résultats Auth E2E (sécurité)
{% if audit_data.artifacts.auth_e2e_results %}
| Étape | Succès | Message |
|-------|--------|---------|
{%- for step in audit_data.artifacts.auth_e2e_results %}
| {{ step.step|md_cell }} | {{ step.success|md_cell }} | {{ (step.error or "validated")|md_cell }} |
{%- endfor %}
{% else %}
Scénario Auth E2E non exécuté.
{% endif %}

### DevEx & Outillage
{% if audit_data.artifacts.devex.indicators %}
| Contrôle | Présent |
|----------|---------|
{%- for key, val in audit_data.artifacts.devex.indicators.items() %}
| {{ key|md_cell }} | {{ val|md_cell }} |
{%- endfor %}
{% else %}
DevEx non évalué.
{% endif %}

### Architecture hexagonale
| Règle | Résultat | Violations |
|-------|----------|------------|
{%- for rule in audit_data.artifacts.hexagonal.rules %}
| {{ rule.rule|md_cell }} | {{ rule.status|md_cell }} | {{ rule.violations_count|md_cell }} |
{%- endfor %}

### Qualité de typage
| Mesure | Valeur |
|--------|--------|
| Occurrences de `any` | {{ audit_data.artifacts.quality.any_count|md_cell }} |
| Fichiers TS/TSX audités | {{ audit_data.artifacts.quality.ts_files|md_cell }} |

### Traçabilité
| Mesure | Valeur |
|--------|--------|
| Statut du fichier | {{ audit_data.artifacts.traceability.status|md_cell }} |
| Nombre de phases tracées | {{ audit_data.artifacts.traceability.phases_count|md_cell }} |
| Nombre total d'échanges (turns) | {{ audit_data.artifacts.trace_metrics.total_turns|md_cell }} |
| Nombre total d'appels d'outils | {{ audit_data.artifacts.trace_metrics.total_tool_calls|md_cell }} |
| Temps réel total (secondes) | {{ audit_data.artifacts.trace_metrics.total_wall_time_seconds|md_cell }} |
| Nombre d'erreurs de trace | {{ audit_data.artifacts.trace_metrics.trace_errors_count|md_cell }} |
| Erreur | {{ audit_data.artifacts.traceability.error|md_cell }} |

### Bonus et malus détectés
| Type | Nom | Détail |
|------|-----|--------|
{%- for bonus in audit_data.artifacts.smells.all_bonuses %}
| bonus | {{ bonus.reason|md_cell }} | detected={{ bonus.status == "OK" }} |
{%- endfor %}
{%- for malus in audit_data.artifacts.smells.all_maluses %}
| malus | {{ malus.reason|md_cell }} | {{ malus.detail|md_cell }} |
{%- endfor %}

### Statistiques techniques
| Mesure | Valeur |
|--------|--------|
| Lignes de code TS | {{ stats.total_lines|md_cell }} |
| Fichiers TS | {{ stats.total_ts_files|md_cell }} |
| Fichiers totaux | {{ stats.total_files|md_cell }} |
| Taille totale (KB) | {{ stats.total_size_kb|md_cell }} |
| Latence moyenne benchmark (ms) | {{ audit_data.artifacts.performance.avg_latency_ms|md_cell }} |

### Arborescence du projet
```text
{{ audit_data.artifacts.project_tree }}
```

---
*Fin du rapport d'audit.*
