---
titre: KPI exploratoires — améliorer le barème sans casser l'historique
type: daf
statut: actif
maj: 2026-11-16
---

# KPI exploratoires et continuité des résultats

Règle posée le 2026-11-16, après une revue de la pertinence des KPI : **un nouveau KPI entre
toujours en « mesuré, non noté »**, et n'est promu en indicateur noté que dans une nouvelle
version de barème.

## Pourquoi

La revue a montré que les barèmes v2/v3 et b1 ne discriminent plus sur ce qu'ils mesurent :

- **Todo** : sur les 12 runs v2 non plafonnés, les trois piliers mesurés sur le livrable
  (78 points) tiennent entre 71,2 et 78 (écart-type 1,9) ; la qualité est à 13/13 partout.
  Traçabilité et coût (22 points, **déclarés par l'agent**) vont de 4 à 18,7 : le classement
  est décidé par la déclaration, pas par le livrable.
- **Blender** : opérationnalité, géométrie et rig sont à 100 % sur les trois runs b1 ; et les
  paliers d'IoU classent Fable 5.1 (IoU 0,28 à 0,35) devant GPT-6 Astra (0,37 à 0,46) sur la
  fidélité visuelle.
- **Tokens déclarés incomparables** : de 1 100 à 129 000 tokens par appel d'outil selon que
  l'agent compte ou non le cache.

Corriger cela en changeant le barème d'un coup aurait rendu les 25 runs publiés incomparables
aux suivants, et obligé à calibrer des bandes sans données.

## La règle

1. Un nouveau KPI est émis par `emit_exploratory()` (`hexa/core/engine/exploratory.py`) dans
   la **phase 8**, en `kind="measured"`. Aucun pilier ne sélectionne cette phase : il ne peut
   pas changer un score (testé : le score recalculé sans la phase 8 est identique).
2. `meta.kpi_revision` dit quel jeu de KPI un rapport a pu mesurer. L'incrémenter
   (`KPI_REVISION`) à chaque ajout ou changement de définition.
3. Un rapport d'avant ces KPI n'est **jamais** complété ni recalculé : son entrée KB ne gagne
   aucune clé, et la KB affiche « non mesurés (audit antérieur) ».
4. Un KPI devient noté seulement dans une nouvelle version (v4, b2), après au moins trois runs
   qui en donnent la dispersion. Les anciennes versions restent rejouables.

## Le repère comparable entre barèmes

La KB affiche, pour **toutes** les entrées, un **score livrable** : les piliers mesurés par
l'auditeur (tout sauf traçabilité et coût), ramenés sur 100, hors bonus, malus et caps. Il est
calculé dans le front à partir de `bucket_scores`, pas dans `data.json` : 17 entrées publiées
n'ont plus de rapport brut et ne pourraient pas être reconstruites.

C'est le repère à citer quand on compare un run v1 et un run v3 (loi n°9). Limite : le
contenu des piliers a un peu bougé entre versions (couverture par couche, pureté du domaine),
il reste donc approximatif entre v1 et v2.

## Jeux 2026-11 et 2026-11.2

| KPI | Bench | Ce qu'il prépare |
|---|---|---|
| Tokens déclarés par appel d'outil, part de cache | tous | contrôle de vraisemblance de la déclaration |
| Tokens, coût et durée lus dans le transcript (`--transcript`) | tous | noter le coût sur du mesuré |
| Duplication, points de décision, plus long fichier, dépendances | Todo | désaturer le pilier Qualité |
| Couverture de branches, latence p95, attente au démarrage | Todo | désaturer l'Opérationnalité |
| Avis de sécurité high/critical distincts, dont en exécution, dont publiés avant la session (jeu 2026-11.2) | Todo | refondre le malus npm (ci-dessous) |
| IoU moyen et minimal en continu | Blender | remplacer les paliers d'IoU |
| Os par membre, os et membres réellement animés par action | Blender | désaturer le pilier Rig |

Les mesures de code sont des **approximations lexicales** (pas de parseur TypeScript) :
comparables d'un livrable à l'autre, pas des valeurs d'outil de référence.

## Le malus npm : fondé, mais mal mesuré (2026-11-16)

Fable 5.2 a perdu 5 points sur « vulnérabilités npm (5 high) », ce qui annule son bonus et
fait l'essentiel de son écart avec Sonnet 5.5 et Opus 5.5 à livrable égal (78/78 pour les
trois). Instruction du cas :

- **Fondé** : les 5 « high » sont 2 avis réels, en dépendances d'exécution (zod 3,
  `@graphql-tools/utils` tiré par Apollo Server 4), publiés les 1er et 5 octobre, soit six
  semaines avant la session. L'agent a choisi des versions majeures anciennes et installé avec
  `--no-audit` : il s'est privé du signal.
- **Mal mesuré** : le malus dépend de la **date d'audit**. Les runs de septembre ont été
  audités avant la publication de ces avis ; ré-audités aujourd'hui avec zod 3, ils prendraient
  le même malus. Il est en tout ou rien (2 avis = 20 avis = −5), compte les paquets dépendants
  et pas les failles, et inclut les dépendances de développement.

Décision de l'utilisateur (2026-11-16), pour le barème v4 :

1. ne compter que les avis **publiés avant la session** de l'agent ;
2. **graduer** le malus par nombre d'avis distincts et par gravité ;
3. ne pénaliser que les dépendances **d'exécution** (`--omit=dev`).

Les trois mesures sont déjà émises en KPI exploratoires (jeu 2026-11.2). La date de
publication vient de l'API publique des avis GitHub ; une date manquante rend le KPI « non
mesuré » plutôt que de conclure à moitié.

## À COMPLÉTER

- Barème **v4** (Todo), à calibrer sur les runs du jeu 2026-11 : bandes d'efficacité monotones
  (aujourd'hui 17 appels d'outils ou 9 minutes font perdre des points), malus gradués (un
  seul malus coûte 5 points et annule le bonus), bonus renouvelés (3 sur 5 obtenus par tous),
  coût noté sur le transcript quand il est fourni.
- Barème **b2** (Blender) : bande des échanges v3 (un agent autonome prend 0/5 en b1), IoU en
  continu, piliers techniques gradués.
- Réduire le poids du déclaratif (22 %) est un **changement de doctrine**, à décider à part.
- Le malus « plus de fichiers de test que de cas exécutés » tombe sur 6 runs v2 sur 12 : à
  vérifier comme faux positif dès qu'un livrable concerné est disponible.
- Silhouette en pose animée (demande un rendu supplémentaire côté Blender), non faite.
