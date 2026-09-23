---
titre: Barème du benchmark Blender (b1)
type: daf
statut: actif
maj: 2026-09-23
---

# Barème Blender b1

Défini dans `blender_bench/bench_config.py`, calculé par le noyau `auditor/engine` (mêmes règles
que la Todo List v2 : indicateurs Fibonacci, bonus plafonné à la moitié de l'écart à 100, caps).
Seuil d'admission commun : 60 %.

| Pilier | Poids | Phase | Mesure |
|---|---|---|---|
| Opérationnalité | 18 | 1 | contrat, build rejoué, export et réimport glTF |
| Géométrie & Topologie | 18 | 2 | intégrité, budget 20–150 k triangles, quads, UV, échelle, parties nommées, 6 appuis |
| Fidélité visuelle | 24 | 5 | IoU FACE/PROFIL/DOS, palette (nœuds + albédo rendu), translucidité, rendus |
| Rig & Animation | 18 | 7 | armature, 6 membres, symétrie, skin ≤ 4 influences, idle/walk, mouvement réel, boucles |
| Traçabilité | 10 | 3 | **identique** à la Todo List (même code) |
| Coût | 12 | 6 | **identique** à la Todo List |

Bonus (phase 4, +5 max) : action supplémentaire, shape keys, textures ≥ 1K, LOD. Malus (−10 max) :
chemin absolu, GLB > 60 Mo, orphelins, maillage non lié à l'armature.

## Caps

| Cap | Max | Déclencheur |
|---|---|---|
| `build_failed` | 40 % | build en erreur, timeout, pas de GLB |
| `sandbox_violation` | 40 % | appel réseau / sous-processus pendant le build |
| `gltf_not_reimportable` | 40 % | le GLB exporté ne se réimporte pas |
| `no_armature` | 50 % | rig absent (obligatoire) |
| `no_real_animation` | 60 % | aucune action ne bouge de ≥ 1 % de la hauteur |

Un **échec de rendu** côté auditeur ne cape pas : la phase 5 tombe, l'opérateur vérifie
l'environnement avant publication (esprit de la loi n°3).

## Pourquoi ce partage

La fidélité visuelle pèse le plus parce que c'est l'objet du défi ; rig et animation pèsent
autant que la géométrie parce qu'ils sont obligatoires et discriminants. Traçabilité et coût
gardent les poids de la Todo List pour que « efficience d'une session » veuille dire la même
chose dans les deux benchmarks — les **scores**, eux, ne se comparent pas d'un benchmark à
l'autre (loi n°9, étendue).

## À COMPLÉTER

- Recaler `DETAIL_BANDS` (calibré sur la seule fixture) et les bandes d'IoU après les premiers runs :
  toute modification → barème b2 et ré-audit (loi n°2).
