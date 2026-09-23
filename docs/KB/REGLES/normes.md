---
titre: Normes de code et de test
type: regle
statut: actif
maj: 2026-07-27
---

# Normes

## Python

Configurées dans `pyproject.toml`, section `[tool.ruff]` — la config fait foi, cette page ne la
duplique pas. Points à connaître :

- Cible **py311**, longueur de ligne **100**, guillemets **doubles**.
- Règles activées : `E`, `F`, `I` (tri des imports), `B` (bugbear), `UP` (modernisation).
- `E501` est **désactivé volontairement** : le formateur possède la longueur de ligne, une URL
  longue ne doit pas faire échouer le lint.
- Sont exclus du lint : `sites/todo/`, `runs/todo/livrables/`, `runs/todo/cr_audits/`, `node_modules/` — du code
  généré ou tiers, qu'on ne normalise pas.

## Tests

- `testpaths = ["hexa/benches/todo/tests"]`, exécution via `pytest`.
- Le `pythonpath` du projet rend `main`, `modules.*`, `kb.*` importables directement : **ne pas
  réintroduire de bricolage `sys.path` dans un fichier de test**, c'est une dette qui a été payée.
- Les tests couvrent l'analyse statique, dynamique, le supply-chain, le scoring, le builder de KB
  et les overrides — tout nouveau checker devrait suivre le même schéma.

## Nommage

- Fichiers de livrable : `AAAAMMJJ_HHMM_<modele>_<effort|temp>` — l'horodatage préfixe permet le
  tri chronologique naturel.
- Rapports d'audit : `cr_<nom_du_livrable>_<horodatage_audit>.{json,md}`.

## Documentation

La KB explique le *pourquoi* et renvoie au code pour le *comment*. Un extrait de code recopié dans
la KB est faux au commit suivant — voir [lois.md](lois.md).
