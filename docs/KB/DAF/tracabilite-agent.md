---
titre: Traçabilité de l'agent — ce qui est auto-déclaré
type: daf
statut: actif
maj: 2026-11-16
---

# Traçabilité de l'agent

L'agent évalué dépose un `audit_trace.json` à la racine de son livrable (format dans
[`README.md`](../../../README.md)). Il vaut 10 % du score au titre de la phase 3 : présence,
validité, cohérence summary ↔ phases (±10 %), et métriques d'efficacité (turns, tool calls,
wall time).

**Mais sa portée réelle est de 22 %.** Depuis le pilier Coût (scoring v2), les compteurs de tokens
du même fichier pilotent aussi les 12 % de la phase 6. Un fichier absent ou menteur ne coûte donc
plus 10 % mais 22 % — près d'un quart du score total repose sur du déclaratif.

## L'invariant à ne jamais oublier

**Ce fichier est rempli par l'agent audité lui-même.** Aucun de ses champs n'est vérifié contre une
mesure externe. En particulier `meta.model`, `meta.prompt_version` et les compteurs d'effort sont
des **déclarations**, pas des observations.

Conséquences opérationnelles :

- Un run peut afficher un modèle qui n'est pas celui réellement utilisé. C'est la raison d'être du
  mécanisme d'overrides — voir [`../DAT/kb-magasin-donnees.md`](../DAT/kb-magasin-donnees.md).
- Comparer deux agents sur leurs métriques d'efficacité déclarées n'a de valeur que si l'on fait
  confiance aux deux déclarations. Le scoring de la phase 3 mesure donc surtout la **discipline**
  (l'agent a-t-il joué le jeu de la traçabilité), pas la performance réelle.

Ne pas « corriger » ce design en supprimant la phase 3 : la discipline déclarative est justement
ce qu'on veut mesurer. Mais ne jamais présenter ces chiffres comme des faits mesurés.

## Le cas particulier du coût

Le pilier Coût mélange déclaré et mesuré, et la nuance compte :

- **les tokens sont déclarés** par l'agent — donc falsifiables comme le reste du fichier ;
- **le prix vient de la table de l'auditeur** (`MODEL_PRICING`) — donc le montant $ ne peut pas
  être auto-déclaré, seulement le volume qui l'alimente.

Un agent qui sous-déclare ses tokens gagne des points sur ce pilier. Le garde-fou n'est pas
technique : les compteurs sont **vérifiables par l'opérateur** dans les outils de session, et
c'est à lui de recouper avant de publier un run frugal suspect.

## Recouper avec une mesure externe

Le recoupement « par l'opérateur » ci-dessus est outillé.

Depuis le 2026-09-22, `hexa/core/tools/session_usage.py` lit le transcript de la session (Claude Code ou
Codex) et en extrait les tokens réels (cache inclus, écritures de cache 5m/1h séparées), le
modèle, l'**effort réel** et la durée, puis les confronte à l'`audit_trace.json`. C'est un outil
d'opérateur : il n'alimente pas le scoring, il sert à lever le doute avant publication.

Pourquoi c'est devenu nécessaire : le pilier Coût (12 % en v2) est calculé sur les tokens déclarés.
Un run peut gagner les 12 points avec des compteurs invraisemblables (p. ex. 33k tokens d'entrée
déclarés pour 38 appels d'outils) pendant qu'un run honnête les perd.

## Depuis le 2026-11-16 : la mesure entre dans le rapport, pas dans le score

`analyze --transcript <session.jsonl>` (Todo et Blender) écrit dans le rapport les tokens, le
coût et la durée lus dans le transcript, l'écart avec la déclaration, et un contrôle de
vraisemblance (tokens déclarés par appel d'outil). Ce sont des KPI exploratoires : ils ne
changent pas le score ([`kpi-exploratoires.md`](kpi-exploratoires.md)). La KB affiche la
source des tokens de chaque entrée (`transcript`, `déclaré`, ou non renseignée pour les
audits antérieurs).

## « Turns » : l'énoncé ne dit pas ce qu'il faut compter

Constaté sur les deux runs du 2026-11-16 (Fable 5.2, Todo et Blender) : pour une session à un
seul message humain, l'agent déclare `total_turns: 12` puis `20`, en comptant les **réponses du
modèle** — et il l'écrit honnêtement dans ses notes. L'auditeur, lui, lit « échanges
User ↔ Agent ». Effet sur le score, à livrable égal :

- Todo v3 (bande 1..2 = 100 %) : 12 → **0/5**, alors que la session est bien autonome ;
- Blender b1 (bande v2 : 5..15 = 100 %, 2..25 = 50 %) : 20 → **2,5/5**, soit mieux que la
  déclaration exacte (1 → 0/5).

L'indicateur note donc la lecture que l'agent fait d'un mot, pas son autonomie. Le transcript
tranche (`user_prompts` de `python3 -m hexa usage`, qui ignore depuis ce jour les notes `isMeta`
du harnais et le modèle `<synthetic>`). Tant que l'énoncé n'est pas précisé (nouvelle
`prompt_version`) ou que l'indicateur ne lit pas le transcript, ne pas commenter un écart de
traçabilité entre deux runs sans regarder ce champ. Une correction opérateur de `total_turns`
n'est **pas** prévue par la procédure (elle ne l'est que pour les tokens) : c'est une décision de
l'utilisateur.

## À COMPLÉTER

- Faut-il faire entrer la mesure du transcript dans le score (et avec quelle règle quand il n'est
  pas disponible, p. ex. runs sur une autre machine) ?
- Faut-il un contrôle de vraisemblance tokens ↔ tool calls ↔ wall time, pour détecter une
  sous-déclaration grossière sans exiger de mesure externe ?
- ~~La bande `total_turns` 5..15 contredit le mode « session entièrement autonome »~~ : corrigé en
  scoring v3 (2026-09-30), bande 1..2 = 100 %, 3..6 = 50 %. Reste ouvert : faut-il ré-auditer en v3
  les runs v2 dont le livrable existe encore, pour les comparer à armes égales ?
