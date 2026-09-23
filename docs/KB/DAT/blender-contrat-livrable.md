---
titre: Contrat du livrable Blender
type: dat
statut: actif
maj: 2026-09-23
---

# Contrat du livrable Blender

L'énoncé fait foi : `blender_bench/challenges/<défi>/enonce.md`. Ce qui suit est ce que
l'auditeur **suppose** pour pouvoir mesurer.

## Dossier

`livrables_blender/AAAAMMJJ_HHMM_<modèle>_<effort>/` (même convention que `livrables/`, dont la KB
tire `session_id` et `agent`). Gitignoré. Depuis le prompt `2609231500`, l'énoncé **impose** à
l'agent de créer ce dossier et d'y travailler, et de ne pas deviner `meta.effort` (`unknown` si
illisible) : le premier run (prompt `2609231100`) avait tout écrit à la racine et déclaré `low` pour
un effort réellement `medium` (lu dans le transcript par `scripts/session_usage.py`, corrigé en
override). Recouper l'effort déclaré avec le transcript fait partie de l'audit.

| Fichier | Exigence |
|---|---|
| `build.py` | Rejouable par `blender -b --factory-startup --python build.py -- --out <dir>` ; à la fin, la scène **contient** le modèle |
| `audit_trace.json` | Même format que la Todo List ([tracabilite-agent](../DAF/tracabilite-agent.md)), `meta.prompt_version` = celle de l'énoncé |
| `README.md` | ≥ 400 caractères |
| `assets/` | Facultatif, lu en relatif à `__file__` |

## Hypothèses dures de l'auditeur

| Hypothèse | Pourquoi |
|---|---|
| Z haut, créature regardant **−Y**, pieds sur z = 0 | Les caméras ortho et le test « posée au sol » en dépendent |
| Os des membres `<membre>_<NN>.<L\|R>` (`serre`, `patte_1`, `patte_2`) | Seul moyen déterministe d'identifier 6 membres, leur symétrie et le cycle de marche |
| Parties nommées par préfixe canonique (`carapace_dorsale`…) sur objet, groupe de sommets ou matériau | Couverture anatomique sans vision par ordinateur |
| Actions `idle` et `walk`, 24 fps | Contrôles d'animation nominatifs |
| Scène = la créature seule | Un sol ou un décor fausse silhouette et bbox |

## Interdits

Réseau, sous-processus, `pip`, chemins absolus. Détection statique (regex, contournable) **et**
à l'exécution (garde-fous de `run_build.py`) ; la seconde déclenche le cap.

## À COMPLÉTER

- Où tournent les sessions d'agent Blender (équivalent de `/home/admin/test/` pour la Todo) ?
