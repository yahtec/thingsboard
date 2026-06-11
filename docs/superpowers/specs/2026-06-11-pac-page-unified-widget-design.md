# Fusion de la page détails PAC hybride en un widget unique

**Date :** 2026-06-11
**État cible :** `donnees_HP1` du dashboard « Mes Installations » (UUID `0964da30-3e56-11f1-bbfe-e1395562cba0`)
**Type de changement :** dashboard REST (POST `/api/dashboard`) — pas de code fork, pas de rebuild/redeploy

## Objectif

Remplacer les **10 widgets** actuels de l'état `donnees_HP1` par **un seul widget markdown** qui rend
l'intégralité de la page. Motivation : supprimer définitivement les espaces de grille gridster et le
double-scroll mobile, et obtenir un contrôle de mise en page pixel-perfect avec un seul fetch réseau.

### État actuel (10 widgets)

| Widget | id | Type |
|---|---|---|
| PAC Info | `49e69aac-15bc-32c4-c32d-c474cfeffa82` | markdown_card |
| Timeline (barre interactive) | `a1b2c3d4-0400-4000-a000-000000000001` | markdown_card |
| PAC Chart Pressions | `a1b2c3d4-0601-4000-a000-000000000001` | markdown_card |
| PAC Chart Températures | `a1b2c3d4-0001-4000-a000-000000000001` | markdown_card |
| PAC Chart Frigo | `a1b2c3d4-0602-4000-a000-000000000002` | markdown_card |
| PAC Chart Compresseur | `a1b2c3d4-0603-4000-a000-000000000003` | markdown_card |
| Chaudière Info | `a1b2c3d4-0002-4000-a000-000000000002` | markdown_card |
| Chaudière Chart (Températures) | `a1b2c3d4-0003-4000-a000-000000000003` | markdown_card |
| Chaudière Chart Brûleur | `a1b2c3d4-0604-4000-a000-000000000004` | markdown_card |
| Répartition d'utilisation (donut) | `a1b2c3d4-9997-4000-a000-000000000097` | tenant.tduo.usage_pie |

## Architecture

**Un seul widget markdown** (id `a1b2c3d4-0700-4000-a000-000000000001`), pleine largeur (col 0, sizeX 24),
pleine hauteur. Toute la page = ce widget. Les cartes markdown TB ne pouvant pas s'imbriquer, c'est la
seule architecture qui donne littéralement « 1 widget ».

Sa `markdownTextFunction` (~1500-2000 lignes) s'organise en briques isolées :

| Brique | Rôle | Origine |
|---|---|---|
| Helpers partagés | `PACV2_FLATTEN`, `PACV2_TO_SERIES`, `getToken`, `getTimeWindow` (lit `sessionStorage tduo.timeline.*` + `tduo.retroview.*`), `getAggInterval` | réutilisés tels quels des charts actuels |
| Fetch unique (courbes+infos) | 1 GET `pac_v2` par tick (fenêtre timeline + intervalle d'agrégation) → flatten → alimente les 6 charts + les 2 infos. **Ne sert PAS le donut** (flux séparé) | nouveau (factorise le cache fetch déjà introduit) |
| Moteur de courbes | `renderChart(svgId, seriesSpec, axisSpec, data, win, evt)` — moteur SVG actuel paramétré, **appelé 6×** | refactor du moteur existant (Fritsch-Carlson, axes multi-échelles, légende cliquable, tooltip, marqueurs evt) |
| Constructeurs info | `buildPacInfo(flatLatest)`, `buildBoilerInfo(flatLatest)` | portés de PAC Info / Chaudière Info |
| Contrôle Timeline | barre sticky (boutons 24h/7j/…, zoom, rétro-vision) ; écrit `sessionStorage` puis déclenche re-fetch/re-render | porté du widget Timeline (fn 3542 car.) |
| Donut Usage | Module autonome : **propre plage** (sélecteur 30j déf., `localStorage`), **propres 3 mini-fetches** (delta compteurs `HP.time`+`boil.time`), split PAC/chaudière/arrêt, rendu donut SVG. **Gating admin/tenant + masquage rétro-vision déjà intégrés**. Flux indépendant du fetch des courbes | porté quasi tel quel du controller `tenant.tduo.usage_pie` (20,6k car.) |
| Marqueurs evt | `__EVT_FETCH` (reconstruction d'intervalles défaut depuis `evt_*`) partagé une fois pour les 6 courbes | réutilisé du chart PAC actuel |

### Spécifications des 6 courbes (séries / axes)

Reprend exactement les choix validés cette session (v289-v293) :

1. **Pressions** — `HPn_pHi` (HP, rouge), `HPn_pLo` (BP, bleu) ; axe gauche 0-45 bar.
2. **Températures** — `HPn_tIn`, `HPn_tOut`, `tExt` ; axe gauche -30-90 °C.
3. **Cycle frigorifique** — `HPn_tOH`, `HPn_tSC`, `HPn_tEvap`, `HPn_tCond` ; axe -30-90 °C.
4. **Compresseur/Détendeur** — `HPn_invert_freq` (Hz), `HPn_invert_pwr` (W, rescale dynamique), `HPn_dpf` (pas).
5. **Températures chaudière** — `HPn_tOut` (entrée), `HPn_boil_tOut` (sortie), `HPn_boil_tSmoke` (fumée).
6. **Brûleur/Circuit eau** — `HPn_boil_qe` (L/h, axe gauche 0-4000), `HPn_boil_rpm` (rpm, 0-7000), `HPn_boil_press` (bar, 0-4).

`n` = index PAC résolu via `ctx.stateController.getStateParams().hpIndex` (préfixe `HPn_`), comme aujourd'hui.

## Flux de données

Deux flux **indépendants** dans le widget :

**(1) Courbes + infos — 1 seul fetch partagé** (fenêtre timeline) :
```
sessionStorage (tduo.timeline.buttonH/zoomPct + tduo.retroview.endTs)
        │  (barre timeline écrit buttonH / zoomPct)
        ▼
getTimeWindow() ──▶ fetch pac_v2 (1×/tick) ──▶ PACV2_TO_SERIES + flatten
        │                                              ├─▶ seriesData ──▶ renderChart ×6
        │                                              └─▶ dernier point ──▶ buildPacInfo / buildBoilerInfo
        ▼
setInterval 30 s (boucle unique) re-fetch + re-render ; cleanup timers/observers au re-mount
```

**(2) Donut Usage — flux séparé** (CORRECTION post-lecture du controller `usage_pie`) :
Le donut **n'utilise pas** le fetch partagé. Il a sa **propre plage** (sélecteur 24h/7j/30j/90j/12m/perso,
défaut **30 j**, mémorisée dans `localStorage tduo.usagePie.range`) et fait **3 mini-requêtes** (compteur
firmware `HPn.HP.time` + `HPn.boil.time` au pré-début, premier-dans-fenêtre, et fin de plage) pour calculer
un **delta de compteurs** → split PAC/chaudière/arrêt. C'est volontairement léger (évite de scanner ~500k
points). Détection d'unité (secondes/heures/bascule) conservée. Le donut **se masque en mode rétro-vision**
(`tduo.retroview.endTs` présent) et porte **déjà** son propre gating admin/tenant (cf. Contrôle d'accès) —
les deux sont portés tels quels.

## Mise en page

- **Frame** : `display:flex; flex-direction:column; height:100%`. Header timeline en `position:sticky; top:0`.
  Le reste en panneau déroulant `overflow-y:auto` (le scroll vit DANS la carte → règle le double-scroll mobile).
- **Sections** empilées : PAC (bandeau info + grille 2×2 de courbes), Chaudière (bandeau info + grille 2×1),
  Usage (donut + légende %).
- **Écartement** : gouttières de quelques pixels entre les objets, vertical ET horizontal (`gap: 6-8px` sur
  les grilles/sections). On ne veut PAS un bloc 100 % jointif — les cartes restent visuellement distinctes,
  juste sans l'espace gridster excessif d'avant.
- **Design plat, pas d'effet 3D** : aucune ombre portée ni élévation (`box-shadow: none`), bordures fines
  `1px solid #e0e0e0` + `border-radius` léger pour délimiter les cartes au lieu des ombres.
- **Responsive piloté en JS** (pas `@media` : le CSS par-widget de TB strippe les media queries — constaté
  cette session). Mesure de `clientWidth` + `ResizeObserver` → grille 2 colonnes si large, 1 colonne si étroit
  (seuil ~600 px). Les courbes ont déjà leur propre détection `narrow` interne.

## Contrôle d'accès (section Usage / donut)

La section **Usage (donut)** n'est rendue que pour les **admins + users tenant**, comme aujourd'hui. Règle
identique à celle du fork (`home.component`) :

- `ctx.currentUser.authority` ∈ {`TENANT_ADMIN`, `SYS_ADMIN`} → visible ; **ou**
- `CUSTOMER_USER` avec attribut serveur `is_admin=true` (déjà mis en cache en `sessionStorage` par
  `home.component`) → visible ;
- sinon la section Usage est **omise du rendu** (pas juste masquée en CSS — on n'effectue même pas son
  agrégation, économie de calcul pour les clients non-admin).

Lecture pratique dans la fonction widget : tester `ctx.currentUser` puis, en repli, `sessionStorage.getItem('is_admin') === 'true'`.

## Gestion d'erreur

- Chaque section (`PAC`, `Chaudière`, `Usage`, chaque courbe) rendue dans un `try/catch` → un échec local
  affiche un encart d'erreur discret, les autres sections restent rendues. **Atténue le single-point-of-failure**
  inhérent à un widget unique.
- Échec du fetch réseau → bannière en tête + conservation du dernier rendu valide (pas d'écran blanc).
- `DEVICE_ID` non résolu (alias) → bail silencieux comme aujourd'hui.

## Découpage incrémental (approche B) — chaque phase = 1 POST réversible

Backup `before_*` avant chaque POST, comme tous les scripts de la session. Pendant les phases 1-4, le widget
unifié est ajouté **au-dessus** des widgets legacy (laissés en place pour comparaison visuelle) ; la phase 5
les retire.

1. **Socle + section PAC** — widget unifié : helpers + fetch partagé + moteur `renderChart` + `buildPacInfo`
   + 4 courbes + grille responsive JS + boucle refresh + try/catch par section. Marqueurs evt branchés.
2. **Section Chaudière** — `buildBoilerInfo` + 2 courbes.
3. **Donut Usage** — lecture du controller `usage_pie`, extraction de la logique d'agrégation + rendu, port
   dans `renderUsage`, **derrière le gate de rôle** (admins + users tenant ; agrégation court-circuitée
   pour les clients non-admin).
4. **Timeline absorbée** — port de la barre interactive dans le header sticky ; suppression du widget Timeline.
5. **Nettoyage** — suppression des 10 widgets legacy ; layout final = 1 seul widget ; vérif finale.

Chaque phase est un script Python idempotent dans `scripts/tb/dashboards/`, sur le modèle des précédents
(login, GET dashboard, backup, mutation, dry-run/offline, POST), avec marker d'idempotence.

## Vérification (à chaque phase)

- `node --check` (node bundlé `ui-ngx/target/node/node.exe`) sur la fonction générée.
- Backup avant POST ; preview offline possible (`--offline <backup>`).
- Validation navigateur **desktop + mobile** par l'utilisateur. Points de contrôle :
  - **1 seul** appel `pac_v2` par tick (onglet réseau) ;
  - marqueurs evt (bandes défaut) présents sur les 6 courbes ;
  - boutons timeline pilotent les 6 courbes simultanément ;
  - toggle légende indépendant par courbe ;
  - sticky header + scroll unique sur mobile (pas de double-scroll, pas de capture par une sous-zone) ;
  - donut : pourcentages cohérents avec l'ancien widget sur la même fenêtre.

## Hors périmètre (YAGNI)

- Pas de changement des autres états du dashboard (menu, default, historique, etc.).
- Pas de nouveau type de widget custom (fork) — tout en markdown_card via REST.
- Le widget `tenant.tduo.usage_pie` n'est pas supprimé du tenant (d'autres états pourraient l'utiliser) ;
  seule son **instance** dans `donnees_HP1` est retirée.

## Risques connus

- **Taille de la fonction** (~2000 lignes) : maintenabilité. Atténué par la structure en briques nommées et
  le moteur unique (vs 6 copies aujourd'hui → c'est en fait une réduction nette de duplication).
- **Sticky dans une carte markdown** : nécessite que le frame soit bien le conteneur de scroll. À valider
  tôt (phase 1).
- **Port du donut** : la logique d'agrégation `usage_pie` (statut HP/boil/arrêt) doit être extraite fidèlement ;
  vérif croisée avec l'ancien donut sur fenêtre identique (phase 3).
- **Coordination avec le customCss mobile** ajouté cette session (touch-action, overflow) : revérifier qu'il
  n'entre pas en conflit avec le scroll interne du widget unique.
