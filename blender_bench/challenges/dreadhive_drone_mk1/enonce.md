# Défi 3D : DREADHIVE — Drone Ravageur Mk.I (Blender)

**Version du prompt : `2609231500`**

---

> ### Mode d'exécution — Session entièrement autonome
>
> Ce cahier des charges est **complet et auto-suffisant**. Vous devez le réaliser sans interaction humaine :
>
> - **Planifiez en amont** : avant la première ligne de code, établissez votre séquence de tâches, vos choix de modélisation et votre découpage en phases. Ce plan ne doit être soumis à personne.
> - **Décidez seul** : ne posez aucune question, ne demandez aucune confirmation ni validation en cours de session. Si un point est ambigu, tranchez en faveur de l'option la plus raisonnée et continuez.
> - **Livrez complet** : l'objectif est un modèle 3D riggé, animé et documenté à l'issue d'une **seule session continue**.

---

## 1. Objectif

À partir de la planche concept fournie (`concept.png`, jointe à cet énoncé), produire dans **Blender** le modèle 3D de la créature **« Unité Xéno — Drone Ravageur Mk.I »**, de la **plus haute qualité possible** : fidèle au concept, propre techniquement, texturé, **riggé** et **animé**, prêt à entrer dans un moteur de jeu (glTF).

La planche contient tout ce dont vous avez besoin :

- **VUE PRINCIPALE 3/4** : l'intention générale, les volumes, l'attitude prédatrice.
- **TURNAROUND** (FACE / PROFIL / DOS) : les **proportions et la silhouette** de référence.
- **DÉTAILS & ÉLÉMENTS** : tête et mandibules, griffe antérieure, plaque dorsale, articulation de patte, sacs toxiques de l'abdomen, coussinets et griffes.
- **EMPILEMENT BIOLOGIQUE** : carapace externe, sous-carapace, faisceaux musculaires, membrane interne, noyau vital.
- **PALETTE COULEUR — XÉNOS** : chitine noire `#171318`, os `#CFC0A5`, chair sombre `#5C2731`, voile nécrose `#603C70`, ambre acide `#C7982A`, vert bile `#657A38`, bleu froid `#31566B`, ichor clair `#DCFEAE`.

La créature a **six membres** : deux **serres antérieures** (grandes faux) et **quatre pattes de ruée**, qui touchent toutes le sol en posture de repos.

## 2. Environnement

- **Blender 4.5 LTS** est installé et utilisable **en ligne de commande, sans interface** (`blender -b …`). L'opérateur vous indique la commande exacte si `blender` n'est pas dans le `PATH`.
- Le moteur de rendu disponible en mode headless est **Cycles (CPU)**. EEVEE et Workbench peuvent ne pas fonctionner sans affichage : ne comptez pas dessus.
- **Aucune ressource externe** : pas d'accès réseau, pas d'installation de paquets (`pip`), pas de modèle, texture ou HDRI téléchargé. Tout ce qui compose le modèle est **produit par votre code** (géométrie, textures procédurales ou générées, rig, animations).
- Vous pouvez (et devriez) **rendre vos propres aperçus** pendant la session pour comparer votre modèle au concept.

## 3. Contrat du livrable

### 3.1 Structure

Créez **d'abord**, dans votre répertoire de travail, le dossier du livrable, puis travaillez
**exclusivement** dedans. Son nom est imposé :

```
./YYYYMMDD_HHMM_[MODEL]_[EFFORT]/
├── build.py            # OBLIGATOIRE — script de construction rejouable
├── README.md           # OBLIGATOIRE — documentation (voir §3.4)
├── audit_trace.json    # OBLIGATOIRE — traçabilité de session (voir §6)
└── assets/             # facultatif — données produites par vous (textures générées, etc.)
```

- `YYYYMMDD_HHMM` : date et heure **locales** de début de session (ex. `20260923_1123`).
- `[MODEL]` : identifiant exact du modèle, tel que `meta.model` (ex. `claude-opus-5-5`).
- `[EFFORT]` : niveau d'effort / de raisonnement **configuré**, tel que `meta.effort`
  (ex. `medium`) ; `unknown` si la plateforme ne l'expose pas.

Exemple : `./20260923_1123_claude-opus-5-5_medium/`. Rien ne doit être écrit hors de ce dossier.

### 3.2 `build.py` — le seul point d'entrée

L'auditeur **rejoue** votre script dans une installation Blender vierge ; il ne regarde **aucun** `.blend`, `.glb` ou rendu que vous auriez produit vous-même. Ce qui compte est ce que `build.py` reconstruit.

- Invocation exacte par l'auditeur :
  ```bash
  blender -b --factory-startup --python build.py -- --out <dossier_de_sortie>
  ```
- Le script part d'une **scène vide** (l'auditeur l'a déjà vidée ; vous pouvez appeler `bpy.ops.wm.read_factory_settings(use_empty=True)` par sécurité).
- **À la fin du script, la scène courante contient le modèle complet** (maillages, matériaux, armature, actions). C'est **l'auditeur** qui sauvegarde le `.blend` et exporte le glTF, avec des réglages identiques pour tous les candidats (`export_apply=True` : vos modificateurs, sauf l'armature, sont appliqués à l'export).
- Vous pouvez écrire des fichiers intermédiaires **uniquement** dans le dossier `--out`. Les ressources livrées dans `assets/` se lisent en chemin **relatif à `__file__`**. Aucun chemin absolu.
- Durée : le script doit se terminer en **moins de 15 minutes** (plus il est rapide, mieux c'est). Un échec ou un dépassement est **éliminatoire**.
- Interdits (détectés, éliminatoires) : sockets / accès réseau, `subprocess`, `os.system`, `pip` / `ensurepip`.

### 3.3 Conventions de scène (contractuelles)

| Sujet | Convention |
| :--- | :--- |
| Unités | Mètres (échelle 1:1). Hauteur totale de la créature en posture de repos : **≈ 2,2 m** (tolérance 1,6 – 3,0 m). |
| Axes | **Z vers le haut.** La créature **regarde vers −Y**. Sa gauche est du côté **+X**. |
| Origine | Au sol (z = 0), sous le centre de la créature. Les pieds posent sur z = 0. |
| Scène | **Uniquement la créature** : pas de sol, décor, caméra ni lumière exportés (l'auditeur éclaire et cadre lui-même). |
| Posture de repos | La pose de repos de l'armature (*rest pose*) est la posture du turnaround. C'est elle que l'auditeur compare aux vues FACE / PROFIL / DOS. |

### 3.4 Nommage (contractuel — l'auditeur s'en sert pour identifier les parties)

**Objets et groupes de sommets** — chaque partie anatomique ci-dessous doit être identifiable par un nom d'objet, de groupe de sommets ou de matériau **commençant** par l'identifiant canonique (suffixes libres, ex. `serre.L`, `patte_1_griffe.R`, `sac_acide_03`) :

| Identifiant | Partie (planche) |
| :--- | :--- |
| `carapace_dorsale` | Carapace dorsale — chitine dure, plaques segmentées |
| `sac_acide` | Sacs acides secondaires / sacs toxiques de l'abdomen |
| `noeud_sensoriel` | Nœud sensoriel (perception / orientation) |
| `mandibule` | Mandibules de rupture |
| `faisceau_musculaire` | Faisceaux musculaires |
| `membrane_ventrale` | Membranes ventrales |
| `serre` | Serres antérieures |
| `patte` | Pattes de ruée |

Aucun objet ne doit garder un nom par défaut (`Cube`, `Sphere.001`, `Cylinder`…).

**Os** — une seule armature. Chaque membre est une chaîne d'os nommée `<membre>_<NN>.<L|R>` avec `NN` sur deux chiffres, `01` à la racine du membre :

| Membre | Chaînes attendues |
| :--- | :--- |
| Serres antérieures | `serre_01.L`, `serre_02.L`, … et `serre_01.R`, `serre_02.R`, … |
| Pattes avant | `patte_1_01.L`, `patte_1_02.L`, … et côté `.R` |
| Pattes arrière | `patte_2_01.L`, `patte_2_02.L`, … et côté `.R` |

Au moins **2 os par membre** (davantage est apprécié : épaule, avant-bras, griffe…). Le tronc, la tête, les mandibules et les sacs peuvent avoir leurs propres os, nommés librement. Les côtés `.L` / `.R` doivent être **symétriques** (miroir en X).

**Actions** — nommées exactement `idle` et `walk` (voir §4.4).

## 4. Exigences de qualité

### 4.1 Fidélité au concept

- **Silhouette et proportions** fidèles au turnaround FACE / PROFIL / DOS : carapace dorsale en crête pointue, tête basse et avancée, serres en faux qui descendent jusqu'au sol, quatre pattes articulées.
- **Couleurs** tirées de la palette XÉNOS : chitine noire sur les plaques, chair sombre sur les muscles, os sur griffes et arêtes, ambre / vert bile / ichor sur les sacs et les fluides.
- Détails de la planche : plaques segmentées, mandibules, nœud sensoriel, sacs translucides, coussinets et griffes.

### 4.2 Géométrie et topologie

- Maillages propres : pas d'arêtes non-manifold, de faces dégénérées ni de sommets isolés ; normales cohérentes (orientées vers l'extérieur).
- Budget : **20 000 à 150 000 triangles** au total (après application des modificateurs).
- Topologie à dominante de quads, peu de n-gones.
- Chaque maillage possède une **UV map** exploitable (peu de chevauchements, coordonnées dans [0, 1]).

### 4.3 Matériaux

- Matériaux **PBR** basés sur le nœud **Principled BSDF**.
- Textures **générées par votre code** (procédurales, ou images créées puis empaquetées / *baked*) : aucune image ne doit manquer.
- Les **sacs acides** et les **membranes** sont **translucides** (Transmission, Subsurface ou Emission).

### 4.4 Rig et animation

- Une **armature** unique ; tous les maillages de la créature y sont liés (modificateur Armature + groupes de sommets).
- **Skinning** : chaque sommet est pondéré, **au plus 4 influences** par sommet (contrainte glTF).
- **Deux actions** obligatoires, à **24 fps**, qui **bouclent** (première et dernière pose identiques) :
  - `idle` — **au moins 48 images** (2 s) : respiration, pulsation des sacs, micro-mouvements de la tête et des mandibules ;
  - `walk` — **au moins 24 images** : cycle de marche où **les quatre pattes** bougent réellement (et les serres accompagnent).
- Toute action supplémentaire (ex. `attack`) est un plus.
- Les actions doivent survivre à l'export glTF (conservez-les : `use_fake_user` ou pistes NLA).

## 5. Ce que l'auditeur vérifie

L'auditeur rejoue `build.py`, sauvegarde la scène, exporte un `.glb` puis le **réimporte**, inspecte la scène et produit ses **propres rendus** (caméras orthographiques FACE / PROFIL / DOS, éclairage imposé, Cycles). La notation est **entièrement automatique et déterministe**, selon six piliers :

| Pilier | Ce qui est mesuré |
| :--- | :--- |
| Opérationnalité | Contrat du livrable, `build.py` qui s'exécute sans erreur, export et réimport glTF |
| Géométrie & Topologie | Intégrité des maillages, budget, quads, UV, échelle, parties nommées, appuis au sol |
| Fidélité visuelle | Silhouettes rendues comparées au turnaround, respect de la palette, translucidité, qualité des rendus |
| Rig & Animation | Armature, membres, symétrie, skinning, actions `idle` / `walk`, mouvement réel, boucles |
| Traçabilité | `audit_trace.json` (§6) |
| Coût & Efficience | Tokens consommés |

## 6. `audit_trace.json`

Fichier de suivi **obligatoire** à la racine du livrable. Il mesure l'efficacité de la session et doit contenir des valeurs réelles (pas des zéros). Indiquez un maximum d'informations sur votre contexte d'exécution dans `meta`.

| Champ | Type | Définition |
| :--- | :--- | :--- |
| `meta.prompt_version` | `string` | Version exacte du présent prompt, à recopier telle quelle : `"2609231500"` |
| `meta.model` | `string` | Le nom exact du modèle d'IA utilisé |
| `meta.temperature` | `number` | La température configurée pour la génération |
| `meta.effort` | `string` | Le niveau d'effort ou de raisonnement **configuré**, lu dans la configuration de la session (ex. `/model`, option `--effort`). Ne le devinez pas : s'il n'est pas lisible, écrivez `"unknown"`. |
| `meta.config` | `object` | Toute autre configuration pertinente de l'agent |
| `summary.total_turns` | `number` | Nombre total d'échanges User ↔ Agent sur la session |
| `summary.total_tool_calls` | `number` | Nombre total d'appels d'outils |
| `summary.total_wall_time_seconds` | `number` | Durée totale réelle de la session en secondes |
| `summary.total_input_tokens` | `number` | **Total des tokens d'entrée, cache inclus.** Sert au calcul du coût (pilier scoré). |
| `summary.total_output_tokens` | `number` | **Total des tokens de sortie.** Sert au calcul du coût. |
| `summary.total_cached_input_tokens` | `number` | *(optionnel)* Sous-ensemble de `total_input_tokens` servi depuis le cache. |
| `phases[].phase` | `number` | Numéro de la phase (§7) |
| `phases[].label` | `string` | Nom court de la phase |
| `phases[].start_time` | `string` | Début de la phase — ISO-8601 UTC, ex : `"2026-09-23T09:00:00Z"` |
| `phases[].end_time` | `string` | Fin de la phase — même format |
| `phases[].turns_in_phase` | `number` | Échanges pendant cette seule phase |
| `phases[].tool_calls_in_phase` | `number` | Appels d'outils pendant cette seule phase |

> `summary` doit être cohérent avec la somme des phases (écart ≤ 10 %). Le coût en dollars est calculé par l'auditeur à partir des tokens : **des tokens absents ⇒ 0 sur le pilier Coût.**

Exemple :

```json
{
  "meta": {"prompt_version": "2609231500", "model": "claude-fable-5-1", "temperature": 1.0, "effort": "high", "config": {}},
  "summary": {"total_turns": 30, "total_tool_calls": 160, "total_wall_time_seconds": 5400,
              "total_input_tokens": 900000, "total_output_tokens": 120000, "total_cached_input_tokens": 600000},
  "phases": [
    {"phase": 1, "label": "Modélisation", "start_time": "2026-09-23T09:00:00Z", "end_time": "2026-09-23T10:00:00Z", "turns_in_phase": 12, "tool_calls_in_phase": 70},
    {"phase": 2, "label": "UV & Matériaux", "start_time": "2026-09-23T10:00:00Z", "end_time": "2026-09-23T10:40:00Z", "turns_in_phase": 9, "tool_calls_in_phase": 45},
    {"phase": 3, "label": "Rig & Animation", "start_time": "2026-09-23T10:40:00Z", "end_time": "2026-09-23T11:30:00Z", "turns_in_phase": 9, "tool_calls_in_phase": 45}
  ]
}
```

## 7. Phases de réalisation

- **Phase 1 — Modélisation** : blocage des volumes d'après le turnaround, puis sculpture procédurale des parties (carapace, tête, mandibules, sacs, membres).
- **Phase 2 — UV & Matériaux** : UV, matériaux PBR, textures générées, palette.
- **Phase 3 — Rig & Animation** : armature, skinning, actions `idle` et `walk`, vérification de l'export glTF.

## 8. README.md

Le `README.md` doit décrire : l'approche de modélisation, la liste des parties et leur correspondance avec la planche, le rig (os, membres), les animations, la commande de construction et les limites connues.

**Attention :** un `build.py` qui échoue, dépasse le délai, ou tente un accès réseau / un sous-processus est éliminatoire.
