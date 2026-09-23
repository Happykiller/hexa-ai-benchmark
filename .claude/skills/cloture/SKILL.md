---
name: cloture
description: Rituel de fin de session de travail. Capitalise les acquis dans docs/KB/, committe et pousse chaque dépôt du projet, exécute les skills de synchronisation de données du projet s'il y en a, arrête les conteneurs du projet, puis vérifie que tout est clean. Fonctionne en autonomie et ne s'arrête que sur anomalie. Déclencher avec /cloture.
---

# /cloture — clore la session de travail

Une session close, c'est trois choses vraies en même temps : **rien d'appris qui soit perdu,
rien d'écrit qui reste non poussé, rien qui tourne encore dans le vide.** Tant que l'une des
trois est fausse, la session n'est pas close — et tu le dis au lieu de conclure.

## Périmètre de ce projet

> À renseigner à l'installation, et à corriger dès que le projet change de forme.

| Dépôt | Chemin | Branche de travail | Remarque |
| --- | --- | --- | --- |
| `hexa-ai-benchmark` | `.` (racine) | `develop` | **Dépôt unique.** Pas de sous-module, pas de dépôt frère : les autres dépôts de `~/` sont d'autres projets, hors périmètre. Un `.git` sous `livrables/<LIVRABLE>/` est le dépôt **créé par l'agent audité** : donnée auditée, gitignorée, ne jamais y committer |

| Stack | Fichier compose | Services |
| --- | --- | --- |
| — | **aucune stack propre au projet** | — |
| *(transitoire)* | `livrables/<LIVRABLE>/docker-compose.yml` | `api`, `mongodb`, `mysql` — stack **du livrable audité**, démarrée par l'auditeur |

| Skill de sync data | Ce qu'il pousse en amont | Doit tourner avant l'arrêt de |
| --- | --- | --- |
| — | *aucun skill de ce type dans ce projet* | — |

**La particularité de ce projet : ses conteneurs ne lui appartiennent pas.** L'auditeur démarre la
stack du livrable qu'il analyse, et le nom du projet compose est le nom du dossier de livrable
(ex. `20260702_0705_claude-fable-5_10`). Conséquences pour la clôture :

- il n'y a **rien à arrêter par défaut** — seulement les stacks qu'un audit a laissées en vie ;
- ces stacks se reconnaissent à leur `CONFIG FILES` pointant dans `livrables/` ;
- `--skip-dynamic` **n'empêche pas** un audit de laisser des conteneurs : les cibles `make`
  passent par Docker (voir `docs/KB/DAT/environnements.md`). Ne jamais supposer qu'un audit
  statique n'a rien démarré — vérifier.

L'auditeur Blender (`blender_bench/`) ne lance **aucun conteneur**, mais un audit interrompu
peut laisser des processus `blender -b` (et leur dossier `/tmp/hexa_blender_*`). Les recenser par
`pgrep -af "blender -b"` et les arrêter nommément (`kill <pid>`) s'ils viennent d'un audit —
jamais un Blender que l'utilisateur aurait ouvert lui-même.

`livrables/` et `cr_audits/` étant gitignorés, un audit ne salit jamais le working tree : un dépôt
propre ne prouve donc **pas** qu'aucun conteneur ne traîne. Les deux contrôles sont indépendants.

Si cette section est vide ou fausse, **recense d'abord** (étape 1) et propose de la corriger dans
le même geste — un périmètre faux fait oublier un dépôt (ou une synchro de données), et un oubli
de ce genre est une session non close qui se croit close.

## Commandes disponibles

| Commande | Action |
| --- | --- |
| `/cloture` | Le rituel complet |
| `/cloture check` | Dry-run : ce qui *serait* fait, dépôt par dépôt, sans rien écrire ni arrêter |
| `/cloture sans-capi` | Saute la capitalisation, déjà faite dans la session |
| `/cloture sans-push` | Committe et arrête, mais ne pousse pas (réseau coupé, travail sensible) |

## Ordre d'exécution — non négociable

```
1. recenser  →  2. capitaliser  →  3. committer  →  4. pousser  →  5. synchroniser les données
→  6. arrêter  →  7. vérifier
```

Les conteneurs tombent **en dernier**, jamais en premier : un hook de pre-commit, une suite de
tests, une migration lancée par la capitalisation, ou une synchro de données peut encore avoir
besoin de la base. Un conteneur arrêté trop tôt transforme une clôture en séance de debug.

## Autonomie et arrêts

Tu enchaînes les six étapes **sans demander de validation**. Tu t'arrêtes net, tu exposes le
problème et tu attends, dans ces cas et ceux-là seulement :

- un **secret** (`.env`, clé privée, token, dump de base, credentials) est sur le point d'être
  committé ;
- un fichier modifié **n'a aucun rapport** avec la session : tu ne sais pas s'il doit partir ;
- un acquis de capitalisation **contredit** une page KB existante — jamais d'écrasement silencieux ;
- un **push rejeté** (non-fast-forward), une branche protégée, ou une règle projet qui impose une
  MR plutôt qu'un push direct ;
- une **synchro de données échoue ou signale un conflit** (remote injoignable, divergence, refus du
  skill lui-même) : tu ne forces rien côté remote, tu rapportes et tu passes à la suite ;
- un **conteneur tourne** sans être rattaché à un compose de ce projet : tu ne l'arrêtes pas ;
- un dépôt **reste sale** après commit (sous-module bougé, artefact non ignoré, conflit) ;
- un dépôt est en état intermédiaire : rebase, merge ou cherry-pick en cours.

## Interdits absolus

Aucun de ces gestes ne se justifie par « pour que ce soit clean » :

- `git push --force` / `--force-with-lease` sans demande explicite ;
- `git add -A` / `git add .` sans avoir lu la liste de ce que ça ajoute ;
- `git reset --hard`, `git checkout .`, `git clean -fd`, `git stash` silencieux — nettoyer, ce
  n'est pas détruire le travail de quelqu'un ;
- `docker compose down -v` (les volumes emportent les données), `docker system prune`,
  `docker stop $(docker ps -q)` ;
- committer sur une branche protégée que les règles du projet réservent aux MR.

> Spécifique à ce projet : ne **jamais** lancer `python3 scripts/build_kb.py --allow-drop` pour
> « débloquer » un rebuild refusé, et ne jamais hand-editer un `cr_audits/*.json`. Ce sont les
> lois n°1 et n°8 (`docs/KB/REGLES/lois.md`) : une entrée publiée dont le rapport brut a disparu
> n'est récupérable nulle part.

## Étape 1 — recenser

```bash
find . -name .git -maxdepth 3 -prune | sed 's|/\.git$||' | sort
find . -maxdepth 3 \( -name 'docker-compose*.y*ml' -o -name 'compose*.y*ml' \) -not -path '*/node_modules/*'
docker compose ls 2>/dev/null
docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}\t{{.Image}}'

# skills de synchronisation de données (même convention que le hook d'accueil)
# -- l'exclusion de /cloture n'est pas cosmétique : sa propre description contient
#    « synchronisation », donc sans elle il se détecte lui-même et s'ajoute à son périmètre.
grep -ril -E 'name: .*sync|description: .*(sync|synchro)' .claude/skills/*/SKILL.md 2>/dev/null \
  | grep -v '/cloture/'
```

> Le `welcome.py` de ce projet **ne fait pas** cette détection (c'est une variante antérieure à
> `collect_sync_skills`). Il n'y a donc pour l'instant qu'un seul motif à maintenir, ici. Si le
> hook gagne un jour cette détection, les deux motifs doivent inclure la même exclusion.

Sur ce projet, le recensement des composes remonte surtout `livrables/*/docker-compose.yml` :
ce sont des **données auditées**, pas des stacks du projet. Seules comptent celles que
`docker compose ls` montre **effectivement en vie**.

Confronte le résultat à la section « Périmètre » et à `docs/KB/DAT/arborescence.md`. Un dépôt
présent sur le disque mais absent du tableau doit être traité **et** signalé. Un skill de sync
data trouvé mais absent du périmètre doit être ajouté au tableau (étape suivante) et signalé.

Ordre de traitement : **les dépôts imbriqués et les dépendances avant le dépôt parent**. Un parent
poussé avant son sous-module pointe vers un commit que personne d'autre ne peut résoudre.

## Étape 2 — capitaliser

Exécute `/capitalize`. En clôture il travaille en autonomie : ce qui passe ses trois filtres
(durable, non déductible, réutilisable) est écrit ; ce qui contredit une page existante est un
**arrêt**, pas un arbitrage que tu rends seul.

Si `/capitalize` n'existe pas dans ce projet, ne l'improvise pas : signale-le, propose de lancer
`factory-ghost`, et poursuis la clôture sans le volet capitalisation.

## Étape 3 — committer, dépôt par dépôt

Pour chaque dépôt du périmètre :

1. `git status --porcelain` et `git diff` — **lis** avant de stager. Ce que tu n'as pas lu, tu ne
   le committes pas.
2. Examine les fichiers non suivis **un par un**. Un artefact de build, un log, un dossier de
   dépendances ne se committe pas : il rejoint `.gitignore` (et c'est un commit à part).
3. **Découpe par sujet**, pas par session. Trois sujets touchés dans la journée font trois
   commits, pas un « wip fin de journée » que personne ne saura relire dans six mois.
4. Message de commit : reprends la convention réelle du dépôt (`git log --oneline -20`) et les
   règles de `docs/KB/REGLES/process.md`. Décris **l'effet obtenu**, pas la liste des fichiers.
5. Ne fabrique pas un commit vide pour « marquer la fin » : un dépôt sans modification reste sans
   commit, et c'est un résultat normal.

> Sur ce projet, `knowledge_base/data.json` est un **dérivé versionné** : s'il apparaît modifié,
> vérifie que le diff ne contient que ce que tu attendais (une entrée ajoutée, pas 36 chemins
> réécrits). Un diff inattendu sur ce fichier est un signal, pas un détail à committer au passage.

## Étape 4 — pousser

Sur la **branche courante** de chaque dépôt, dans l'ordre de l'étape 1. Jamais de force.

Si le push est rejeté : ne rebase pas d'office, ne force pas. Rapporte l'écart
(`git rev-list --left-right --count @{upstream}...HEAD`) et laisse la décision.

Si les règles du projet imposent une MR sur cette branche, pousse la branche de travail et
**donne le lien de création de MR** au lieu de pousser sur la cible.

## Étape 5 — synchroniser les données

Pour chaque skill de sync data du périmètre : exécute-le maintenant, **avant** l'arrêt des
conteneurs — c'est le pendant, côté clôture, de la détection que fait l'accueil de session côté
ouverture : ce que le hook d'accueil a pu tirer du remote en début de session, ce skill le pousse
vers le remote en fin de session.

**Sur ce projet, cette étape est un no-op** : aucun skill de sync data n'existe. Dis-le
explicitement et passe à la suite — n'improvise pas une synchro. Si un tel skill apparaît un jour,
relance `factory-ghost` pour l'inscrire au périmètre plutôt que de l'appeler à la volée.

- Un skill qui échoue ou signale un conflit est un **arrêt** (cf. « Autonomie et arrêts »), pas une
  synchro que tu forces ou que tu ignores en silence.
- Si `/cloture sans-push` a été demandé, applique la même prudence à la synchro de données : elle
  aussi pousse vers un remote, donc elle est sautée pour la même raison, et signalée comme telle.

## Étape 6 — arrêter les conteneurs

Uniquement ce qui appartient au projet, stack par stack, depuis le dossier du compose :

```bash
docker compose -f <fichier> down       # sans -v : les volumes survivent
```

Ici, `<fichier>` sera typiquement `livrables/<LIVRABLE>/docker-compose.yml` — la stack qu'un audit
a laissée derrière lui. Ne pas ajouter `-v` : si les volumes doivent repartir vierges, c'est
l'auditeur qui le fait, avec son propre `--fresh-docker`, au prochain audit.

Un conteneur du projet lancé hors compose s'arrête nommément (`docker stop <nom>`). Tout ce qui
n'est pas identifié comme appartenant au projet **reste en vie** et part dans le rapport.

## Étape 7 — vérifier

La clôture n'est pas ce que tu as fait, c'est ce qui est vrai à la fin. Prouve-le :

```bash
# Chaque dépôt : working tree propre et rien en attente de push
for r in <dépôts du périmètre>; do
  printf '%-24s ' "$r"
  [ -z "$(git -C "$r" status --porcelain)" ] && printf 'clean  ' || printf 'SALE   '
  git -C "$r" rev-list --left-right --count @{upstream}...HEAD 2>/dev/null \
    | awk '{print ($1==0 && $2==0) ? "sync" : "retard/avance: "$1"/"$2}'
done

# Plus aucun conteneur du projet
docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}'
```

Si le périmètre a des skills de sync data, leur résultat (poussé / échoué / no-op) est vérifié ici
au même titre qu'un push : une synchro non confirmée n'est pas une session close.

Contrôle propre à ce projet : `docker compose ls` ne doit plus lister aucune stack pointant dans
`livrables/`.

## Étape 8 — rendre compte

Court, factuel, et honnête sur ce qui n'a pas pu être refermé :

```
## Clôture — hexa-ai-benchmark

Capitalisation : 2 pages KB enrichies, 1 créée, 1 ligne HISTORY, 0 outil.

| Dépôt             | Commits | Push       | État final |
| ---               | ---     | ---        | ---        |
| hexa-ai-benchmark | 3       | ok develop | clean      |

Synchro de données : aucune synchro de données pour ce projet.

Conteneurs : stack de livrable `20260702_0705_claude-fable-5_10` arrêtée (2 services).
Aucun conteneur du projet encore en vie.

Non refermé :
- (rien)
```

S'il n'y a rien dans « Non refermé », écris-le explicitement. **La session est close** est une
affirmation vérifiée, pas une formule de politesse.
