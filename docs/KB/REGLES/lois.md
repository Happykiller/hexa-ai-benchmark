---
titre: Lois — invariants non négociables
type: regle
statut: actif
maj: 2026-09-22
---

# Lois du projet

Ce qu'on ne fait **jamais** ici, et pourquoi.

## 1. Ne jamais hand-editer un `cr_audits/*.json` ou son `.md` jumeau

C'est la source brute immuable produite par l'auditeur. La modifier détruit la trace de ce qui a
réellement été mesuré, et la modification saute au prochain rebuild. Toute correction passe par
`knowledge_base/overrides.json`.
→ [`../DAT/kb-magasin-donnees.md`](../DAT/kb-magasin-donnees.md)

## 2. L'outillage n'influence jamais le scoring

La config de lint, de test ou de formatage ne doit avoir **aucun** effet sur les scores produits.
C'est écrit en tête de `pyproject.toml`. Un audit doit rester comparable à ceux d'il y a six mois.

## 3. Ne jamais publier un run à 40 % sans avoir levé le doute sur le cap

Un cap peut venir de l'environnement d'audit (bind-mounts `root:root`) et non du livrable.
Publier sans vérifier, c'est diffamer un modèle.
→ [`../DAT/environnements.md`](../DAT/environnements.md)

## 4. Ne jamais présenter les métriques d'`audit_trace.json` comme mesurées

Elles sont **auto-déclarées par l'agent audité**. Elles mesurent la discipline, pas la performance.
Depuis le pilier Coût (scoring v2), cela couvre aussi les **compteurs de tokens**, donc 22 % du
score et non plus 10 %. Le montant $ affiché, lui, vient de la table de prix de l'auditeur : il est
calculé, pas déclaré — mais il est calculé *sur* une déclaration.
→ [`../DAF/tracabilite-agent.md`](../DAF/tracabilite-agent.md)

## 5. Ne jamais recopier du code dans la KB

La KB porte les invariants et les décisions ; le code porte l'implémentation. Un extrait recopié
devient une seconde source de vérité qui divergera.

## 6. Une seule source d'instructions agent : `CLAUDE.md`

Le projet est **unifié sur Claude Code** (décision du 2026-07-27). `AGENTS.md`, `CODEX.md` et
`GEMINI.md` ont été supprimés : leur contenu durable a été reversé dans cette KB. Ne pas les
recréer, et ne pas laisser `CLAUDE.md` enfler — il pointe vers la KB, il ne la duplique pas.

## 7. L'outillage Claude est versionné, le local ne l'est pas

`.claude/skills/`, `.claude/agents/` et `.claude/hooks/` sont **dans le dépôt** : ils font partie du
projet au même titre que l'auditeur. Seul `.claude/settings.local.json` reste ignoré — il porte des
permissions propres à la machine.

Conséquence : ajouter ou modifier un skill/agent/hook est un **changement de projet**, à committer
et à refléter dans [`../MOTEUR.md`](../MOTEUR.md). Ne rien y mettre de spécifique à une machine
(chemins absolus, secrets, préférences personnelles).

## 8. Ne jamais faire disparaître une entrée publiée de la KB

`data.json` est versionné, `cr_audits/` ne l'est pas : une entrée dont le rapport brut a disparu
n'est récupérable **nulle part**. Un rebuild complet qui la supprimerait est refusé par le builder ;
`--allow-drop` n'est légitime qu'après avoir relu le diff et décidé de la perte.

Un run publié est un résultat opposable à un modèle. Le retirer sans trace, c'est réécrire le
palmarès.
→ [`../DAT/kb-magasin-donnees.md`](../DAT/kb-magasin-donnees.md)

## 9. Ne jamais comparer des scores v1 et v2 sans le dire

Les barèmes diffèrent (50/25/15/10 sans coût, contre 43/22/13/10/12) et les règles de plafond aussi.
Le modèle de scoring est affiché dans le détail de chaque entrée ; c'est à celui qui commente le
palmarès de ne pas mettre deux barèmes sur la même ligne.
→ [`../DAF/piliers-notation.md`](../DAF/piliers-notation.md)

## 10. Ne jamais lancer un audit pendant qu'une session d'agent tourne

Même en `--skip-dynamic` : `make lint/build/test` passent par `docker compose run`, qui démarre
mongodb/mysql. Un agent en cours teste sa propre stack sur les ports mêmes de l'auditeur
(4000 / 47017 / 43306). Auditer à ce moment-là fausse **les deux** mesures : l'auditeur note l'API
de l'agent, et son teardown détruit la stack d'un run en cours.
→ [`../DAT/environnements.md`](../DAT/environnements.md)
