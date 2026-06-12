# Spec — Page ECS (eau chaude sanitaire) : état `ecs` + widget unifié

**Date** : 2026-06-12
**Dashboard** : Mes Installations (`0964da30-3e56-11f1-bbfe-e1395562cba0`)
**Statut** : approche A validée par JE le 2026-06-12

## Objectif

Ajouter un écran ECS sur le modèle de `depart_chauffage` : timeline des températures
ECS + tableaux des pompes, accessible depuis la carte « Module ECS » de l'état
`default`.

## Architecture (approche A — clone du pattern heat-unified)

- Nouvel état **`ecs`** (« Eau chaude sanitaire »), `autoFillHeight`, contenant **un
  seul widget markdown** id `a1b2c3d4-0720-4000-a000-000000000001`.
- Source : `scripts/tb/dashboards/_src/ecs-unified.fn.js` (+ `ecs-unified.css`),
  dérivée de `heat-unified.fn.js`, namespace `window.__tbEcsUnified`.
- Déploiement REST pur (pas de rebuild fork) : `deploy-ecs-widget.py` (modèle
  `deploy-heat-widget.py`) + patch de la carte ECS pour la navigation.
- ⚠ leçon depart_chauffage : ne jamais laisser d'autre widget sur un état
  `autoFillHeight`.

## Détection du type de module

`pac_v2.type` : **0 = sans module, 1 = chauffage seul, 2 = ECS seul,
3 = chauffage + ECS** (firmware vérifié, aucune autre valeur ; parc actuel = 0/1).

- Carte « Module ECS » de l'état `default` : cliquable (hover + « Voir détails → »,
  `data-ecsnav` → `goState('ecs')`) **uniquement si type ∈ {2, 3}**.
- Page ECS : si type ∈ {0, 1} (accès direct par URL), message
  « Pas de module ECS sur cette installation ».

## Timeline (courbe)

Même barre timeline/rétroview/zoom que les autres pages (clés sessionStorage
`tduo.timeline.*` et `tduo.retroview.endTs` partagées). Séries extraites de
`pac_v2` via `PACV2_TO_SERIES`/`PACV2_FLATTEN` (le flatten gère déjà `dhw`) :

| Série | Clé flatten | Affichage | Condition |
|---|---|---|---|
| T° entrée | `dhw_tIn` | bleu, axe °C | toujours |
| T° sortie | `dhw_tOut` | rouge, axe °C | toujours |
| T° ballon | `dhw_tTank` | couleur tierce, axe °C | points tracés ssi **5 ≤ v ≤ 90 °C** |
| Position V3V | `dhw_posV3V` | axe % secondaire (droite, 0–100) | type = 3 |
| T° entrée module | `tInM` **ou** `TinM` | axe °C | type = 3 |

⚠ `tInM`/`TinM` : les deux casses existent sur le parc (2602* envoient `TinM`).
Le flatten copie les scalaires top-level tels quels → résolveur
`v = flat.tInM !== undefined ? flat.tInM : flat.TinM`.

Convention existante conservée : valeurs sentinelles ignorées (seuil moteur ≤ −45,
qui attrape aussi le −47.8 firmware et la sentinelle interne −99.9).

## Tableaux pompes

Grille 2×2 sous la courbe. Valeurs = dernière valeur reçue (ou valeur à la date
rétroview), via fetch latest séparé — même mécanique que la table calo de la page
chauffage (la timeline ne recadre que la courbe).

Sélection des pompes selon le type :

| Position | type = 3 (chauffage+ECS) | type = 2 (ECS seul) |
|---|---|---|
| Haut gauche | « Pompe primaire échangeur 1 » `dhw_pump1_*` | « Pompe 1 module » `pump1M_*` |
| Haut droite | « Pompe primaire échangeur 2 » `dhw_pump2_*` (si présente) | « Pompe 2 module » `pump2M_*` (si présente) |
| Bas gauche | « Pompe secondaire échangeur 1 » `dhw_pump3_*` | idem |
| Bas droite | « Pompe secondaire échangeur 2 » `dhw_pump4_*` (si présente) | idem |

Lignes de chaque tableau (5 champs firmware) :

| Ligne | Clé | Unité affichée |
|---|---|---|
| ΔP | `*_dP` | bar |
| Puissance | `*_pwr` | W |
| Débit | `*_qe` | m³/h |
| Vitesse | `*_rpm` | tr/min |
| Temps de marche | `*_time` | h |

Unités de ΔP, débit et temps **à confirmer à la validation visuelle** (valeurs
plausibles observées : dP 5.8, qe 3.1 m³/h, time 330 h sur pump2M de 2623001001).

**Présence pump2/pump4 et pump2M (provisoire)** : tableau affiché si au moins un
des 5 champs est non nul dans le **dernier pac_v2 reçu** (le compteur `time` est
cumulatif, donc une pompe ayant déjà tourné reste détectée même à l'arrêt). L'automate enverra prochainement
des clés de présence dédiées dans le payload : ce sont des **paramètres statiques**,
figés à la mise en service (modifiés uniquement sur demande client, ex. ajout d'une
pompe) → il suffira de les lire dans le dernier pac_v2 reçu, sans logique de fenêtre.
Le critère est isolé dans une fonction `pumpPresent()` pour que la bascule soit un
changement d'une seule fonction.

## Hors périmètre

- Pas de consigne `dhw_tSet` sur la timeline (non demandé).
- Pas de modification de la page chauffage ni du widget unified PAC.
- Bascule sur les futures clés automate (présence pompes) : chantier ultérieur.

## Validation

Parc actuel sans module ECS (type 0/1) → validation limitée : rendu de la page en
accès direct (garde « Pas de module ECS »), rendu type forcé en local si besoin,
valeurs à zéro. Validation complète quand une installation type 2/3 sera en ligne.

## Déploiement

1. `deploy-ecs-widget.py` : crée/replace l'état `ecs` + le widget (backup avant POST,
   idempotent, `--dry-run`).
2. `patch-ecs-nav-card.py` : rend la carte « Module ECS » du widget « Données
   générales » cliquable si type ∈ {2,3} (marker idempotent, backup).
