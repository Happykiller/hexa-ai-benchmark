---
titre: Défi Blender — modéliser une créature d'après une planche concept
type: daf
statut: actif
maj: 2026-09-23
---

# Défi Blender

## L'épreuve

L'agent reçoit une **planche concept** et un énoncé, et doit livrer dans Blender le modèle 3D de
la plus haute qualité possible, **riggé et animé** (idle + marche), prêt pour un moteur de jeu.
Premier défi du catalogue : `dreadhive_drone_mk1`, « Unité Xéno — Drone Ravageur Mk.I » (planche
DREADHIVE fournie par l'utilisateur, versionnée avec son accord le 2026-09-23).

Ce que le défi cherche à révéler : la capacité d'un agent à **voir** une référence (turnaround,
palette, détails), à la traduire en géométrie **par le code** (pas d'interface, pas d'asset
externe), puis à mener un pipeline complet jusqu'au rig et à l'animation — là où les modèles
décrochent le plus.

## Catalogue

`blender_bench/challenges/<id>/` = `concept.png` + `enonce.md` + `spec.json` (boîtes des vues du
turnaround, palette, vocabulaire des parties et des os, budget, animations, profil de rendu).
Ajouter un défi = ajouter un dossier ; `--challenge <id>` le sélectionne.

## Limites assumées de la mesure

- **Silhouettes** : les vignettes du turnaround font ~140×260 px, en légère perspective, avec
  ombres et coulures ; les rendus sont orthographiques. Un excellent modèle plafonne vers 0,7
  d'IoU, d'où des bandes basses (0,25 / 0,40 / 0,55).
- La fidélité « artistique » (qualité des formes, lisibilité) n'est mesurée qu'indirectement
  (silhouette, palette, détail de surface). Aucun juge LLM : le benchmark reste déterministe.
- Le profil est comparé aussi en miroir : l'orientation gauche/droite n'est pas un critère.

## À COMPLÉTER

- Obtenir la planche source en haute résolution et, idéalement, les trois vues orthographiques
  séparées sur fond uni (`views.*.source` dans `spec.json` est prévu pour ça) : la mesure de
  silhouette gagnerait en précision sans changer le code.
- Premier vrai run : calibrer `DETAIL_BANDS` et les bandes d'IoU sur des modèles réels.
