---
titre: Piliers de notation et seuils
type: daf
statut: actif
maj: 2026-09-22
---

# Piliers de notation

**Cinq** piliers depuis le scoring v2 (2026-06-08), poids détaillés dans
[`README.md`](../../../README.md) : Opérationnalité 43 %, Architecture 22 %, Qualité logicielle
13 %, Discipline & Traçabilité 10 %, Coût & Efficience 12 %, plus un bonus/malus (+5 / −10).

## L'intention derrière les poids

Le gros du score porte sur **est-ce que ça marche**. C'est un choix : un livrable élégant qui ne
démarre pas vaut moins qu'un livrable modeste qui tourne. Toute proposition de rééquilibrage doit
être discutée comme un changement de doctrine, pas comme un réglage.

Le pilier **Coût** a été introduit parce qu'un livrable identique obtenu en brûlant vingt fois plus
de tokens n'est pas la même performance d'agent. Les 12 % ont été pris sur les trois premiers
piliers (50/25/15 → 43/22/13) pour que le total reste 100.

## Deux générations de scoring cohabitent

| Modèle | Piliers | Où on le voit |
|---|---|---|
| `indicator_fibonacci_v1` | 50 / 25 / 15 / 10, pas de pilier Coût | Runs d'avant juin 2026 |
| `indicator_fibonacci_v2` | 43 / 22 / 13 / 10 / 12 | Défaut depuis le 2026-06-08 |

`--scoring v1` rejoue les scores historiques à l'identique — c'est la raison d'être du flag, pas une
option de confort. **Conséquence à ne jamais perdre de vue : classer un run v1 et un run v2 dans un
même palmarès compare deux barèmes différents.** La KB affiche le modèle de scoring dans le détail
de chaque entrée (`Modèle scoring : fib_v1|fib_v2`) ; le classement, lui, ne le distingue pas.

## Le bonus n'est pas symétrique du malus (v2)

Les malus se soustraient en plein, puis le bonus ne comble que **la moitié de l'écart restant à
100 %** (`BONUS_HEADROOM_FRACTION = 0.5`). Une base à 99 avec bonus plein plafonne à 99,5.

C'est délibéré : en v1, le bonus pouvait compléter une base imparfaite jusqu'à 100 %, et les bons
modèles se tassaient tous sur 100. Le 100 % est désormais réservé à une base sans défaut.

## Les caps éliminatoires

| Condition | Score plafonné à |
|---|---|
| `make build` échoue | 40 % |
| Scénario E2E fonctionnel échoue | 40 % |
| Stack non démarrée : scénario E2E non exécutable (`runtime_not_started`) | 40 % |

Le troisième cap ferme une inversion : sans lui, un livrable dont `make start` échoue (toutes les
étapes E2E en `SKIPPED`, aucun cap) dépassait un livrable qui démarre mais rate **une** étape E2E.
`--skip-dynamic` reste non plafonné : c'est un choix de l'opérateur, pas un échec du livrable.

Le cap n'est pas une pénalité graduée : c'est un verdict. Il existe parce qu'au-delà d'un certain
point, les autres mesures perdent leur sens — noter la qualité du typage d'un projet qui ne
compile pas n'informe personne.

**Piège**: un cap à 40 % peut être causé par l'environnement d'audit et non par le livrable
(bind-mounts `root:root` — voir [`../DAT/environnements.md`](../DAT/environnements.md)). Toujours
lever ce doute avant de publier un run à 40 %.

## Seuil d'admission

**≥ 60 % = ADMIS**, sinon ÉCHEC. Le seuil est binaire et affiché tel quel dans la KB.

## Modèle de pondération des indicateurs

`indicator_fibonacci_v2` : chaque contrôle produit un **indicateur** pondéré selon sa position
(Fibonacci) ou un poids explicite, la valeur est rangée dans une **bande** qui donne un ratio, et
les indicateurs s'agrègent en buckets normalisés sur 100. Les maluses sont de polarité négative.

L'intérêt de ce modèle : ajouter un contrôle ne demande pas de re-répartir des pourcentages à la
main. L'inconvénient : un même contrôle peut peser différemment selon l'ordre des indicateurs dans
son étape — d'où la prudence à avoir en réordonnant.
