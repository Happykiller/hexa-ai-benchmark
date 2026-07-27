---
titre: Magasin de données KB — brut, overrides, dérivé
type: dat
statut: actif
maj: 2026-07-27
---

# Magasin de données de la knowledge base

La KB n'est **pas un snapshot** : c'est une chaîne à trois étages, et c'est la décision
d'architecture la plus structurante du volet KB.

| Étage | Fichier | Nature |
|---|---|---|
| Brut | `cr_audits/*.json` (+ `.md` jumeau) | Produit par l'auditeur. **Immuable.** |
| Correction | `knowledge_base/overrides.json` | Corrections manuelles, tracées et réversibles, keyées par id d'entrée |
| Dérivé | `knowledge_base/data.json` | Recalculé depuis brut + overrides |

## Pourquoi des overrides plutôt qu'une édition directe

Certaines métadonnées d'une entrée (`model`, `effort`, `prompt_version`) proviennent de
l'`audit_trace.json` **auto-déclaré par l'agent audité** : elles sont donc parfois fausses, sans
que le score le soit. Corriger à la source détruirait la trace de ce que l'agent a réellement
déclaré, et la correction disparaîtrait au prochain rebuild.

Les overrides résolvent les deux : la correction est **visible** (les entrées corrigées portent une
section « Corrections manuelles » dans le rendu) et **rejouable**. Le merge est *shallow*, au
niveau top de l'entrée.

Conséquence directe : **ne jamais hand-editer un `cr_*.json`** — c'est une loi du projet, voir
[`../REGLES/lois.md`](../REGLES/lois.md).

## Rebuild complet vs upsert

`scripts/build_kb.py` (wrapper mince de `kb/builder.py`) sait faire les deux : reconstruire toutes
les entrées, ou n'ajouter/mettre à jour qu'une entrée par son id. L'upsert existe parce qu'un
rebuild complet relit et re-parse tous les rapports markdown — inutile quand un seul audit vient
de tomber. Commandes exactes : [`README.md`](../../../README.md).

## Le package `kb/`

`normalizer.py` (chargement/normalisation des audits), `markdown_parser.py` (extraction des
constats depuis les rapports `.md`), `render.py` (sections normalisées consommées par le front),
`constants.py` (chemins partagés), `builder.py` (orchestration).

Le parsing markdown existe parce que le `.json` ne contient pas tout : une partie des constats
n'est lisible que dans le rapport rendu. C'est une dépendance fragile — **si le template
`auditor/templates/report.md` change de structure, `markdown_parser.py` peut casser
silencieusement**. Les deux évoluent ensemble.
