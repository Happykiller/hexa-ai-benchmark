---
titre: Piliers de notation et seuils
type: daf
statut: actif
maj: 2026-09-22
---

# Piliers de notation

Quatre piliers, dont les poids sont détaillés dans [`README.md`](../../../README.md) :
Opérationnalité 50 %, Architecture 25 %, Qualité logicielle 15 %, Discipline & Traçabilité 10 %,
plus un bonus/malus (+5 / −10).

## L'intention derrière les poids

La moitié du score porte sur **est-ce que ça marche**. C'est un choix : un livrable élégant qui ne
démarre pas vaut moins qu'un livrable modeste qui tourne. Toute proposition de rééquilibrage doit
être discutée comme un changement de doctrine, pas comme un réglage.

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

## Modèle de score

`indicator_fibonacci_v2` : chaque contrôle produit un **indicateur** pondéré selon sa position
(Fibonacci) ou un poids explicite, la valeur est rangée dans une **bande** qui donne un ratio, et
les indicateurs s'agrègent en buckets normalisés sur 100. Les maluses sont de polarité négative.

L'intérêt de ce modèle : ajouter un contrôle ne demande pas de re-répartir des pourcentages à la
main. L'inconvénient : un même contrôle peut peser différemment selon l'ordre des indicateurs dans
son étape — d'où la prudence à avoir en réordonnant.
