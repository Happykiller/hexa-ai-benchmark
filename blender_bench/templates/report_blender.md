# Rapport d'audit — Benchmark Blender 3D
**Cible :** {{ audit_data.meta.target_path }}
**Défi :** {{ audit_data.meta.challenge_label }} (`{{ audit_data.meta.challenge }}`, prompt `{{ audit_data.meta.expected_prompt_version }}`)
**Date début :** {{ audit_data.meta.audit_started_at }}
**Date fin :** {{ audit_data.meta.audit_finished_at }}
**Modèle de score :** {{ audit_data.meta.scoring_model }}
**Blender :** {{ audit_data.meta.blender_version }}{% if audit_data.meta.skip_render %} — **rendus désactivés (--skip-render) : score non publiable**{% endif %}

---

## Résumé global
| Mesure | Valeur |
|--------|--------|
| Points positifs gagnés | {{ audit_data.summary.positive_points_earned|md_cell }} |
| Points positifs possibles | {{ audit_data.summary.positive_points_possible|md_cell }} |
| Malus cumulés | {{ audit_data.summary.negative_points|md_cell }} |
| Score brut (Net) | {{ audit_data.summary.raw_total_score|md_cell }} |
| Score normalisé de base | {{ audit_data.summary.normalized_base_score|md_cell }}/{{ audit_data.summary.normalized_base_weight_total|md_cell }} |
| Règle de plafond (scoring) | {{ audit_data.summary.scoring_version|md_cell }} |
| Malus appliqué | {{ audit_data.summary.bonus_malus_adjustment.capped_malus|md_cell }} |
| Bonus effectif (comble du plafond) | {{ audit_data.summary.bonus_malus_adjustment.effective_bonus|md_cell }} |
| Pourcentage brut du score net | {{ audit_data.summary.raw_percentage_net|md_cell }}% |
| Pourcentage final du score net | {{ audit_data.summary.percentage_net|md_cell }}% |
| Coût de la session ($) | {{ audit_data.summary.cost_usd|md_cell }} |
| Tokens totaux (in+out) | {{ audit_data.summary.total_tokens|md_cell }} |
| Valeur (points de score par $) | {{ audit_data.summary.cost_efficiency_pct_per_usd|md_cell }} |
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
{%- set build = audit_data.artifacts.build or {} %}
### Rejeu de build.py
| Mesure | Valeur |
|--------|--------|
| Statut | {{ build.build_status|md_cell }} |
| Durée (s) | {{ build.build_seconds|md_cell }} |
| Scène sauvegardée | {{ build.saved|md_cell }} |
| GLB exporté | {{ build.exported|md_cell }} ({{ audit_data.stats.glb_mb|md_cell }} Mo) |
| Erreur | {{ (build.error or build.runner_error or build.export_error or "aucune")|md_cell }} |
| Appels interdits | {{ (build.violations or [])|length }} |
{% if build.traceback %}
```text
{{ build.traceback }}
```
{% endif %}

### Exécutions Blender
| Script | Statut | Code | Timeout | Secondes |
|--------|--------|------|---------|----------|
{%- for run in audit_data.artifacts.blender_runs %}
| {{ run.script|md_cell }} | {{ run.status|md_cell }} | {{ run.exit_code|md_cell }} | {{ run.timed_out|md_cell }} | {{ run.seconds|md_cell }} |
{%- endfor %}

### Statistiques
| Mesure | Valeur |
|--------|--------|
| Triangles | {{ audit_data.stats.triangles|md_cell }} |
| Maillages | {{ audit_data.stats.meshes|md_cell }} |
| Matériaux | {{ audit_data.stats.materials|md_cell }} |
| Os | {{ audit_data.stats.bones|md_cell }} |
| Actions | {{ audit_data.stats.actions|join(", ")|md_cell }} |
| Hauteur (m) | {{ audit_data.stats.height_m|md_cell }} |
| IoU FACE / PROFIL / DOS | {{ audit_data.stats.iou.front|md_cell }} / {{ audit_data.stats.iou.side|md_cell }} / {{ audit_data.stats.iou.back|md_cell }} |
| ΔE moyen du rendu vers la palette | {{ audit_data.stats.palette_delta_e|md_cell }} |

{% if audit_data.artifacts.media %}
### Visuels
{%- for item in audit_data.artifacts.media %}
{%- if item.kind != "video" %}
- {{ item.label }} : ![{{ item.label }}]({{ item.path }})
{%- else %}
- {{ item.label }} : [{{ item.file }}]({{ item.path }})
{%- endif %}
{%- endfor %}
{% endif %}

### Traçabilité
| Mesure | Valeur |
|--------|--------|
| Statut audit_trace.json | {{ audit_data.artifacts.traceability.status|md_cell }} |
| Erreur | {{ (audit_data.artifacts.traceability.error or "aucune")|md_cell }} |
| Modèle déclaré | {{ audit_data.artifacts.trace_metrics.model|md_cell }} |
| Tours / appels d'outils / secondes (auto-déclarés) | {{ audit_data.artifacts.trace_metrics.total_turns|md_cell }} / {{ audit_data.artifacts.trace_metrics.total_tool_calls|md_cell }} / {{ audit_data.artifacts.trace_metrics.total_wall_time_seconds|md_cell }} |

> Les métriques de `audit_trace.json` sont déclarées par l'agent audité, pas mesurées (loi n°4).

### Fichiers Python du livrable
{%- for file in audit_data.artifacts.static.python_files %}
- `{{ file }}`
{%- endfor %}
