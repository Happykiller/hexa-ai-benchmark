---
titre: Pipeline de l'auditeur Blender
type: dat
statut: actif
maj: 2026-09-23
---

# Pipeline de l'auditeur Blender

`python3 blender_bench/cli.py analyze livrables_blender/<NOM>` — second benchmark du dépôt,
autonome : seul le noyau `auditor/engine/` est partagé avec la Todo List.

## Enchaînement

| Étape | Où | Produit |
|---|---|---|
| Contrôles statiques | `blender_bench/static_checks.py` (hôte) | contrat, imports interdits, chemins absolus |
| Rejeu du build | `bpy_scripts/run_build.py` (dans Blender) | `build_log.json`, `scene.blend`, `model.glb` |
| Inspection | `bpy_scripts/inspect_scene.py` | `inspection.json` (géométrie, UV, skin, os, actions) |
| Aller-retour glTF | `bpy_scripts/reimport_gltf.py` | `reimport.json` |
| Rendus | `bpy_scripts/render_views.py` (3 modes) | vues ortho albédo + beauty, turntable, planches d'animation |
| Analyses | `blender_bench/analysis/` (hôte, numpy + Pillow) | des `Check` → indicateurs (`emit.py`) |
| Score | `auditor/engine` avec le barème `bench_config.py` | `cr_audits_blender/cr_<livrable>_<ts>.{json,md}` + `_media/` |

Principe : **les scripts bpy mesurent, l'hôte note**. Aucun seuil dans `bpy_scripts/` ; les
analyses sont des fonctions pures testées sans Blender sur une inspection figée
(`blender_bench/tests/fixtures/inspection/`).

## Pourquoi l'auditeur rejoue `build.py`

On ne note que ce que l'auditeur produit lui-même. Un `.blend` livré ne dit pas comment il a été
fait ; un script rejoué dans une installation vierge (`--factory-startup`) si. C'est aussi
l'auditeur qui sauvegarde et **exporte** (réglages glTF identiques pour tous).

## Exécution de Blender

`blender_bench/runner.py` : `blender -b [scene.blend] --factory-startup -noaudio -t 8
--python-exit-code 1`, env minimal (`HOME`, `TMPDIR`, config Blender dans le dossier de travail),
groupe de processus tué au timeout (`timeouts_s` de `spec.json`). Binaire : `--blender` >
`$HEXA_BLENDER_BIN` > `blender` du PATH > `~/.local/bin/blender45` (Blender 4.5 LTS est **hors
PATH** sur la machine de référence). Le livrable est **copié** dans le dossier de travail avant
rejeu : un build ne peut pas polluer `livrables_blender/`.

Garde-fous de `run_build.py` : `socket`, `subprocess.Popen`, `os.system` & co remplacés par des
stubs qui journalisent puis lèvent → cap `sandbox_violation`. **Ce n'est pas une isolation**
(loi n°11) : un script hostile peut s'en défaire.

## Rendus déterministes

- **Cycles CPU** imposé : EEVEE et Workbench demandent OpenGL, absent sous WSL2 (pas de
  `/dev/dri`) ; CUDA donne d'autres pixels que le CPU et dépend de 4 Go de VRAM.
- Seed, échantillons et threads figés ; échantillonnage adaptatif, débruitage et path guiding
  coupés. Deux rendus donnent des **pixels** identiques (`test_normalized_render_is_deterministic`,
  opt-in `HEXA_BLENDER_SLOW=1`). Les fichiers PNG, eux, diffèrent : Cycles y écrit ses temps de
  rendu. Les visuels publiés sont ré-encodés par Pillow (aucune métadonnée).
- Caméras orthographiques FACE (−Y), PROFIL (**−X**, tête à droite comme la planche), DOS (+Y).
  Caméras, lumières et monde du livrable sont supprimés.
- Rendu `flat` = **passe albédo** (Diffuse Color + Transmission Color composées) : mesurer la
  palette sur l'image éclairée faisait passer la chitine noire brillante pour du bleu froid
  (reflet du monde blanc). L'alpha donne la silhouette.

## Variables d'environnement

| Variable | Effet |
|---|---|
| `HEXA_BLENDER_BIN` | Binaire Blender |
| `HEXA_BLENDER_AUDIT_OUTPUT_DIR` | Remplace `cr_audits_blender/` (tests) |
| `HEXA_BLENDER_SLOW=1` | Active les tests de rendu (≈ 1 min) |

Options utiles : `--skip-render` (itération rapide, phase 5 en SKIPPED : **non publiable**),
`--keep-work` puis `--reuse-work <dossier>` (réanalyser sans relancer Blender).

## À COMPLÉTER

- Durée réelle d'un audit sur un modèle de 150 k triangles (fixture : 60 s rendus compris).
- Faut-il une isolation forte (conteneur) avant d'auditer des livrables d'origine externe ?
