# Spec — Historique événements : masquer l'icône diagnostic quand pas de snapshot

**Date** : 2026-06-12
**Widget cible** : `tduo.events_history` (id `af86baf0-3fe1-11f1-bbfe-e1395562cba0`)
**Statut** : validé par JE le 2026-06-12

## Problème

L'icône « Voir diagnostic » (colonne Action) s'affiche pour tout événement avec un
code défaut (type 1 ou 4), sans savoir si un snapshot existe. Or certains défauts
n'ont jamais de snapshot :

- **Défauts liés au module** (unités 60–68) : pas de snapshot d'office, par design firmware.
- **Défauts communication PAC** : la PAC est injoignable, le TDUO ne peut pas capturer
  les arrays debug.
- **Firmware verrouillé** après un défaut précédent : snapshot non envoyé alors que le
  type de défaut en aurait normalement un.

L'utilisateur clique et tombe sur la page « Aucun snapshot disponible » du widget
`fault_diagnostic` — cul-de-sac.

## Comportement cible

**Pas d'icône du tout** quand aucun snapshot n'existe pour le défaut. Cellule Action
vide. Invariant : icône visible ⇔ la page diagnostic trouvera un snapshot.

Le widget `fault_diagnostic` n'est pas modifié : sa page « Aucun snapshot » reste le
filet de sécurité.

## Détection : hybride (règle statique + probe dynamique)

### 1. Règle statique — cas sûrs, appliquée dans `_actionCell`

Pas d'icône si :

- `evt_device` ∈ **60–68** (Module, Pompe 1/2 module, Calorimètre module, Chauffage,
  Calorimètre chauffage, ECS, Pompe primaire/secondaire ECS) ; **ou**
- `evt_device` ∈ **50–55** (PAC Hybride 1–6) **et** `evt_fault` ∈ codes communication
  **{15, 29, 38, 39, 40}**.

Les codes incertains (84–87 « Defaut com. pompe/compresseur/gaz », internes à la PAC)
ne sont **pas** dans la liste statique — le probe tranche.

**Amendement post-vérification prod (2026-06-12)** : le fault **88 est retiré** de la
liste statique — un événement (dev 51, fault 88) avait un snapshot dans la fenêtre en
prod ; le probe dynamique tranche pour le 88. Règle module confirmée en prod
(36 événements dev 60–68, 0 snapshot). Faults 15/29/38/39/40 : aucune occurrence en
prod, conservés sur foi de la spec firmware.

### 2. Probe dynamique — le reste

Dans `onDataUpdated`, après `_pair()` :

- **Une seule** requête télémétrie REST sur les 8 clés probe du diagnostic :
  `p_bp, p_hp, t_bp, t_hph, wp_b, b_s, pb_spd, pe_spd` ;
- fenêtre = `[min(evtTs) − 120 s, max(evtTs) + 60 s]` sur l'ensemble des événements
  chargés, `limit=1000` (par clé ; les snapshots sont rares — un par défaut), `agg=NONE` ;
- on en tire la liste triée des timestamps de snapshots ;
- une ligne **a** un snapshot s'il existe un ts dans `[evtTs − 120 s, evtTs + 60 s]`
  — même fenêtre que `fault_diagnostic`, garantissant l'invariant icône ⇔ snapshot.

L'ancrage `evtTs` par ligne suit la même logique que `_actionCell` actuel :
`appearTs || resolvedTs || ts`.

### 3. Chargement, cache, erreurs

- Premier rendu **sans** icônes ; re-rendu quand le probe répond (pas de flash
  d'icônes mortes).
- Résultat du probe mis en cache, invalidé quand la fenêtre temporelle des données
  change (comparaison min/max ts des événements).
- **Échec du probe** (erreur réseau/HTTP, devId ou token indisponible) : repli sur
  la règle statique seule — icônes affichées pour les non-exclus (dégradation vers
  le comportement actuel, on ne masque jamais tout par erreur) — et cache invalidé
  pour retenter au prochain rafraîchissement des données.
- **Réponse tronquée** (une clé atteint `limit=1000`) : liste de snapshots incomplète
  → repli sur la règle statique seule (on préfère des icônes en trop que masquées à
  tort) ; pas de retry (re-fetcher ne ramènerait pas plus de points).

## Déploiement

- Script idempotent `scripts/tb/widgets/patch-events-history-hide-no-snapshot.py`
  sur le modèle des patches existants : marker `__EVTHIST_NOSNAP_PATCH__`, backup
  JSON avant POST dans `scripts/tb/backup/widgets-tduo-v1/`, login + GET/POST
  `/api/widgetType`.
- Validation sur un device prod ayant des défauts module et un défaut comm PAC
  connus : vérifier icône absente pour ces lignes, présente pour un défaut PAC
  avec snapshot confirmé.
