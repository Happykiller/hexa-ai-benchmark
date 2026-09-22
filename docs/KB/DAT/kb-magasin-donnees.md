---
titre: Magasin de données KB — brut, overrides, dérivé
type: dat
statut: actif
maj: 2026-09-22
---

# Magasin de données de la knowledge base

La KB n'est **pas un snapshot** : c'est une chaîne à trois étages, et c'est la décision
d'architecture la plus structurante du volet KB.

| Étage | Fichier | Nature | Versionné ? |
|---|---|---|---|
| Brut | `cr_audits/*.json` (+ `.md` jumeau) | Produit par l'auditeur. **Immuable.** | **non** |
| Correction | `knowledge_base/overrides.json` | Corrections manuelles, tracées et réversibles, keyées par id d'entrée | oui |
| Dérivé | `knowledge_base/data.json` | Recalculé depuis brut + overrides | oui |

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

## L'asymétrie de versionnement, et le garde-fou qui en découle

C'est le point le plus dangereux du magasin : **le dérivé est versionné, la source ne l'est pas.**
`cr_audits/` est dans `.gitignore` (les rapports sont volumineux et rejouables *en principe*), alors
que `data.json` est commité parce qu'il est lu au runtime par le front.

Conséquence : un `cr_*.json` supprimé, ou produit sur une autre machine, laisse une entrée publiée
**sans source**. Un rebuild complet la ferait alors disparaître de la KB, silencieusement, sans que
rien n'échoue — et git ne peut pas la restaurer puisque le brut n'y a jamais été.

`build_knowledge_base()` **refuse donc d'écrire** quand le rebuild ferait perdre des entrées déjà
publiées (`KnowledgeBaseShrinkError`), et liste les ids concernés. Trois issues :

1. restaurer les `cr_*.json` manquants dans `cr_audits/`, puis rebuild ;
2. passer par `--add`, qui ne touche qu'une entrée ;
3. `--allow-drop`, qui assume la suppression — après relecture de
   `git diff knowledge_base/data.json`.

Ne jamais choisir (3) par réflexe pour « débloquer » la commande : c'est exactement le geste que le
garde-fou existe pour empêcher.

## Le dérivé doit être reproductible bit à bit

`data.json` est versionné : deux façons de produire la même entrée doivent donner le **même
texte**, sinon chaque build fait du bruit dans git et masque les vrais changements.

Le piège rencontré : le rebuild complet stockait des chemins **absolus** (issus de `SCAN_DIRS`)
tandis que `--add` stockait ce que l'appelant avait tapé. Résultat, 36 champs `source_file`
portaient des préfixes de deux machines différentes (`/home/happykiller/sandbox/…`,
`/home/admin/sandbox/…`), et tout `--add` en réécrivait un au hasard. `repo_relative()`
(`kb/constants.py`) normalise désormais ces chemins en relatif-dépôt, à la normalisation — donc
en un seul endroit, pour les deux chemins de code.

À retenir pour la suite : **aucun chemin machine ne doit entrer dans `data.json`**. Les chemins
qui apparaissent dans les *sorties capturées* (logs npm, erreurs make) sont une autre affaire —
ce sont des preuves de ce que le run a affiché, on n'y touche pas.

**Ampleur selon la machine.** Sur la machine `admin` (2026-09-22), ce n'étaient pas 2 mais 17 des
19 entrées publiées qui n'avaient pas leur `cr_*.json` local : l'upsert (`--add`) est la **voie par
défaut**, pas une optimisation. Question ouverte : versionner les bruts (p. ex.
`knowledge_base/raw/`) pour rendre la KB réellement régénérable.

**Ré-audit d'un même livrable ≠ perte d'entrée.** Quand un correctif de l'auditeur impose de
ré-auditer un livrable, le nouveau cr porte un nouvel id : l'ancienne entrée est retirée de
`data.json` pour ne pas publier deux fois le même run, et ses overrides sont reportés sur le nouvel
id. Le run reste publié ; la trace est le cr brut d'origine (conservé) et le commit `kb(...)` qui
donne ancien → nouveau score. Cas du 2026-09-22 : claude-opus-5 75,78 → 82,0 %, gpt-5.6-sol
88,51 → 89,19 %.

**Limites des overrides.** Ils sont cosmétiques : surcharger `model` ne recalcule ni le coût ni le
score (figés dans le cr par l'auditeur), et le merge shallow remplace un objet imbriqué en entier
(`cost`). Une erreur de tarif ne se corrige que par un nouvel audit.

## Le package `kb/`

`normalizer.py` (chargement/normalisation des audits), `markdown_parser.py` (extraction des
constats depuis les rapports `.md`), `render.py` (sections normalisées consommées par le front),
`constants.py` (chemins partagés), `builder.py` (orchestration).

Le parsing markdown existe parce que le `.json` ne contient pas tout : une partie des constats
n'est lisible que dans le rapport rendu. C'est une dépendance fragile — **si le template
`auditor/templates/report.md` change de structure, `markdown_parser.py` peut casser
silencieusement**. Les deux évoluent ensemble.
