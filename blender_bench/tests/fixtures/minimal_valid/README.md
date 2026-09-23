# Drone Ravageur Mk.I — livrable témoin

Livrable de test de l'auditeur Blender (`blender_bench`) : une créature construite en
primitives, conforme au contrat de l'énoncé mais volontairement pauvre en détail.

## Approche
Volumes en ellipsoïdes et cônes (bmesh), UV générées à la création, un matériau Principled
par famille de la palette XÉNOS. Les sacs acides sont translucides (Transmission) et les
membranes diffusent (Subsurface).

## Parties
`carapace_dorsale`, `sac_acide.L/R`, `noeud_sensoriel`, `mandibule.L/R`,
`faisceau_musculaire_corps`, `membrane_ventrale`, `serre.L/R`, `patte_1.L/R`, `patte_2.L/R`.

## Rig et animations
Armature `rig_drone` : `racine`, `tete`, puis deux os par membre (`serre_01.L`,
`serre_02.L`…). Chaque maillage est pondéré à 100 % sur un os. Actions `idle` (49 images,
respiration) et `walk` (25 images, pattes en diagonale), bouclées, 24 fps.

## Construction
`blender -b --factory-startup --python build.py -- --out sortie/`
