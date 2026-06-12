# Fusion de la page Départ chauffage en widget unique

**Date :** 2026-06-12
**État cible :** `depart_chauffage` du dashboard « Mes Installations » (UUID `0964da30-3e56-11f1-bbfe-e1395562cba0`)
**Type de changement :** dashboard REST (POST `/api/dashboard`) — pas de code fork, pas de rebuild

## Objectif

Remplacer les **4 widgets** de l'état `depart_chauffage` par **un seul widget markdown**, sur le modèle
exact de la fusion PAC (`donnees_HP1`, livrée 2026-06-11). Réutilise le harness `unified.fn.js`.

### État actuel (4 widgets)
| Widget | id | Rôle |
|---|---|---|
| Chauffage Header | `a1b2c3d4-0502-4000-a000-000000000001` | titre « Départ chauffage » + bouton rétroview + date (aucune valeur) — dérivé de PAC Info |
| Chauffage Info (calo) | `a1b2c3d4-0500-4000-a000-000000000001` | table calorimètre `heat_calo_*` + décodage unités Mainone |
| Timeline | `a1b2c3d4-0400-4000-a000-000000000002` | barre fenêtre 4/8/12/24h + zoom |
| Chauffage Chart | `a1b2c3d4-0501-4000-a000-000000000001` | 1 courbe : consigne/départ/retour/T°ext |

## Architecture

**Un widget markdown** `a1b2c3d4-0710-4000-a000-000000000001` remplace les 4. Nouveaux fichiers
`scripts/tb/dashboards/_src/heat-unified.fn.js` + `heat-unified.css`. Les cartes markdown TB ne pouvant
pas s'importer entre elles, on **duplique le moteur** depuis `unified.fn.js` (code prouvé) en ne gardant
que ce qui sert au chauffage.

Briques **réutilisées telles quelles** de `unified.fn.js` :
- helpers `PACV2_FLATTEN`, `PACV2_TO_SERIES`, `getToken`, `resolveDevice`, `getTimeWindow`, `getAggInterval` ;
- moteur `renderChart(cfg, seriesData, win, evt)` (Fritsch-Carlson, multi-axe, légende, tooltip, `isBadChart`) ;
- `fetchEvt` + `__EVT_RECTS` (marqueurs défaut) ;
- la barre **timeline + rétroview** (`buildTimelineBar`/`wireTimelineBar`, picker `window.__tbvPicker`, gating
  `TENANT_ADMIN`/`SYS_ADMIN`/`is_admin`/`access_retroview`, curseur zoom inversé 100%↔5%) ;
- `infoTable(rows, lblPx, valPx)`, `safe(tag, fn)`, `wireResponsiveGrid`, cleanup `window.__tbHeatUnified`
  (namespace distinct de `__tbPacUnified` pour cohabiter sans collision).

Briques **spécifiques chauffage** :
- `buildCaloInfo(e)` : table calorimètre portée de `heat_info_calo.fn.js` (CALO_UNITS Mainone + `caloRow`),
  rendue en **tableau inline** (le CSS scopé TB ne s'applique pas au contenu injecté), **police 14/18**
  comme les tableaux PAC/chaudière.
- 1 spec de courbe `HEAT_CHART` : séries `heat_setpoint` (consigne, vert), `heat_tOut` (départ, rouge),
  `heat_tIn` (retour, bleu), `tExt` (extérieure, gris) ; axe gauche **−20..90 °C**.

## Mise en page (validée)

Colonne unique (`autoFillHeight` déjà activé sur l'état → remplit le viewport, scroll interne unique) :
1. **Titre** « Départ chauffage » (hors cadre, plat).
2. **Barre Timeline + Rétroview** pleine largeur, sticky.
3. **Rangée [ table calo (gauche, demi-largeur) | courbe chauffage (droite, demi-largeur) ]** —
   flex 2 colonnes en desktop, **wrap en 1 colonne** sur mobile (piloté JS, seuil ~600 px).

## Flux de données

Identique à la PAC :
- **fetch fenêtré** `pac_v2` (fenêtre timeline) → la courbe (`HEAT_CHART`) ;
- **fetch latest** (`limit=1&orderBy=DESC`, endTs = now ou rétroview) → la table calo (dernière valeur reçue,
  ou valeur à la date rétroview) ;
- la timeline ne recadre **que la courbe** ; la table calo est indépendante de la fenêtre ;
- boucle 30 s unique, cleanup timers/observers/listeners au re-init ; `try/catch` par section.

## Gating

Le bouton rétroview reste gated (`TENANT_ADMIN`/`SYS_ADMIN`, ou `CUSTOMER_USER` avec `is_admin` ou
`access_retroview`). Pas de donut ici → pas de section admin-only supplémentaire.

## Découpage (réutilise le harness, plus court que la PAC)

1. **Phase 1 — widget complet** : `heat-unified.fn.js` (titre + barre timeline/rétroview + rangée
   calo|courbe), `heat-unified.css`, script de déploiement `deploy-heat-widget.py` (upsert + layout,
   `node --check`, idempotent, pousse les legacy sous row 100). Déploiement → vérif desktop+mobile.
2. **Phase 2 — nettoyage** : `retire-legacy-heat-widgets.py` retire les 4 widgets legacy (0502/0500/0400-…-0002/0501),
   ne garde que `0710` plein écran.

Backup avant chaque POST ; `node --check` avant chaque déploiement (node bundlé `ui-ngx/target/node/node.exe`).

## Vérification

- Table calo demi-largeur à gauche, police 14/18, unités Mainone décodées ; courbe à droite.
- 1 fetch `pac_v2`/30 s pour la courbe ; table calo = dernière valeur (ou date rétroview).
- Timeline recadre la courbe ; rétroview fonctionne ; marqueurs défaut présents.
- Mobile : calo puis courbe empilées, scroll unique, pas de double-scroll.

## Hors périmètre (YAGNI)

- Pas de jauges, donut, chaudière (page chauffage seule).
- Les autres états du dashboard inchangés.
- Le widget unifié PAC (`donnees_HP1`/`0700`) inchangé.

## Risques

- Duplication du moteur (~heat-unified.fn.js volumineux) : atténué — code prouvé, sous-ensemble du PAC.
- Cohabitation des globals : namespace `window.__tbHeatUnified` distinct de `__tbPacUnified` ; `window.__tbvPicker`
  est partagé (un seul picker rétroview par page, idempotent) — OK puisque une seule page affichée à la fois.
- CSS scopé TB inopérant sur contenu injecté → tout en styles inline (déjà la règle).
