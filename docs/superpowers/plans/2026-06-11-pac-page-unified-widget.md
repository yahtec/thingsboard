# Fusion page PAC hybride en widget unique — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** Remplacer les 10 widgets de l'état `donnees_HP1` (dashboard « Mes Installations ») par un seul widget markdown rendant timeline, infos PAC/chaudière, 6 courbes et donut d'usage.

**Architecture :** Un widget `markdown_card` dont la `markdownTextFunction` retourne le squelette HTML (header timeline sticky + sections) puis, dans un `setTimeout`, résout le device, lance une boucle de fetch `pac_v2` partagée (1 requête → 6 courbes + 2 infos) et — si admin — un module donut autonome (sa propre plage + ses propres requêtes). Construit de façon incrémentale (approche B) : on enrichit `_src/unified.fn.js` section par section et on re-POST à chaque phase, les widgets legacy restant visibles dessous jusqu'au nettoyage final.

**Tech Stack :** ThingsBoard 4.3 markdown_card (JS vanilla, SVG inline), API REST `/api/dashboard`, scripts Python 3 (urllib), validation `node --check` via `ui-ngx/target/node/node.exe`.

**Référence spec :** `docs/superpowers/specs/2026-06-11-pac-page-unified-widget-design.md`

**Sources extraites (canoniques, déjà dumpées) :** `scripts/tb/dashboards/_src/`
- `pac_chart_temperatures.fn.js` (31,5k) — moteur de courbes complet à paramétrer
- `pac_chart_temperatures.css` (1,5k) — CSS frame/chart
- `pac_info.fn.js` (34,6k) / `pac_info.css` (8,1k) — builder info PAC + thème
- `boiler_info.fn.js` (6,9k) — builder info chaudière (PACV2_FLATTEN + buildValueRow + tH)
- `timeline.fn.js` (3,5k) — barre boutons 4/8/12/24h + slider zoom (écrit sessionStorage)
- `usage_pie.controller.js` (20,6k) — module donut (plage propre, 3 mini-fetches, agrégation, SVG, gating admin, masquage rétroview)

---

## Constantes partagées (utilisées par tous les scripts)

```
BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
STATE_ID     = 'donnees_HP1'
USER         = 'je@yahtec.com'
NODE         = r'c:\Projets\TB\thingsboard\ui-ngx\target\node\node.exe'

# Widget unifié (nouveau)
WID_UNIFIED  = 'a1b2c3d4-0700-4000-a000-000000000001'

# Widgets legacy (à retirer en phase 5)
WID_PAC_INFO   = '49e69aac-15bc-32c4-c32d-c474cfeffa82'
WID_TIMELINE   = 'a1b2c3d4-0400-4000-a000-000000000001'
WID_CH_PRESS   = 'a1b2c3d4-0601-4000-a000-000000000001'
WID_CH_TEMP    = 'a1b2c3d4-0001-4000-a000-000000000001'
WID_CH_FRIG    = 'a1b2c3d4-0602-4000-a000-000000000002'
WID_CH_COMP    = 'a1b2c3d4-0603-4000-a000-000000000003'
WID_BOIL_INFO  = 'a1b2c3d4-0002-4000-a000-000000000002'
WID_BOIL_TEMP  = 'a1b2c3d4-0003-4000-a000-000000000003'
WID_BOIL_BRUL  = 'a1b2c3d4-0604-4000-a000-000000000004'
WID_PIE        = 'a1b2c3d4-9997-4000-a000-000000000097'
LEGACY_WIDS = [WID_PAC_INFO, WID_TIMELINE, WID_CH_PRESS, WID_CH_TEMP, WID_CH_FRIG,
               WID_CH_COMP, WID_BOIL_INFO, WID_BOIL_TEMP, WID_BOIL_BRUL, WID_PIE]
```

## Structure de fichiers

```
scripts/tb/dashboards/
  _src/
    unified.fn.js     # CONSTRUIT incrémentalement (phases 1→4). La markdownTextFunction finale.
    unified.css       # CRÉÉ en phase 1, complété si besoin. Le markdownCss du widget.
    (+ les 6 dumps canoniques déjà présents)
  deploy-unified-widget.py   # CRÉÉ en phase 1. Upsert du widget unifié + layout. Réutilisé à chaque phase.
  retire-legacy-pac-widgets.py  # CRÉÉ en phase 5. Retire les 10 widgets legacy de l'état.
  _lib_tb.py          # CRÉÉ en phase 1. Helpers login/get/post/backup partagés (DRY).
```

**Modèle de travail par phase :** on édite `_src/unified.fn.js` (ajout d'une section), on valide `node --check`, puis on lance `deploy-unified-widget.py --pwd <pwd>` qui : login → GET dashboard → backup → upsert `WID_UNIFIED` (fn = contenu de `unified.fn.js`, css = `unified.css`) → applique le layout de la phase courante → POST. Idempotent (il écrase toujours le widget par le contenu courant des fichiers).

---

## Task 1 : Harness — helpers TB + script de déploiement réutilisable

**Files:**
- Create: `scripts/tb/dashboards/_lib_tb.py`
- Create: `scripts/tb/dashboards/deploy-unified-widget.py`
- Create: `scripts/tb/dashboards/_src/unified.css`
- Create: `scripts/tb/dashboards/_src/unified.fn.js` (stub minimal, complété en Task 2+)

- [ ] **Step 1 : Écrire `_lib_tb.py`** (helpers DRY)

Contenu complet : login / token_or_login / http_get / http_post / get_dashboard / backup / post_dashboard.
Voir le bloc « _lib_tb.py » en annexe A du présent plan (code complet, à recopier tel quel).

- [ ] **Step 2 : Écrire `_src/unified.css`** — voir annexe B (thème plat, gouttières 6px, sticky).

- [ ] **Step 3 : Écrire le stub `_src/unified.fn.js`** :

```javascript
// __PAC_UNIFIED_V1__  (stub - remplace en Task 2)
return '<div class="u-root"><div class="u-scroll"><div class="u-err">unified stub</div></div></div>';
```

- [ ] **Step 4 : Écrire `deploy-unified-widget.py`** — voir annexe C (upsert widget + layout par phase + `node --check`).

- [ ] **Step 5 : Valider en dry-run**

Run: `python -X utf8 scripts\tb\dashboards\deploy-unified-widget.py --pwd <pwd> --phase 1 --dry-run`
Expected : `node --check OK`, `backup: ...`, `widget upsert + layout phase 1`, `[dry-run] preview: ...`. Aucun POST.

- [ ] **Step 6 : Commit**

```
git add scripts/tb/dashboards/_lib_tb.py scripts/tb/dashboards/deploy-unified-widget.py scripts/tb/dashboards/_src/unified.css scripts/tb/dashboards/_src/unified.fn.js
git commit -m "feat(scripts/tb): harness widget PAC unifie (lib + deploy + stub)"
```

---

## Task 2 : Socle + section PAC (info + 4 courbes, fetch partagé, responsive)

**But :** `_src/unified.fn.js` rend le squelette complet (header timeline placeholder + section PAC + sections vides chaudière/usage), résout le device, fait 1 fetch `pac_v2` partagé, et rend `buildPacInfo` + 4 courbes via un moteur unique `renderChart`. Chaque rendu est protégé par try/catch.

**Files:**
- Modify: `scripts/tb/dashboards/_src/unified.fn.js` (remplace le stub)

### Structure cible de `unified.fn.js` (ordre des blocs)

```
// __PAC_UNIFIED_V1__
// [A] helpers : PACV2_FLATTEN, PACV2_TO_SERIES, getToken, getTimeWindow, getAggInterval
// [B] ctxRef + resolveHpIndex/resolveDevice/getToken DEFINIS ICI (avant [C]) ;
//     calculer var P = resolveHpIndex(ctxRef); var pre = 'HP'+P+'_';
//     IMPORTANT : ctxRef est un `var` — il DOIT etre assigne avant que [C] s'evalue,
//     sinon pre vaut toujours 'HP1_'. Ne pas repousser ces defs dans le setTimeout [E].
// [C] SECTIONS config : tableau des 6 specs de courbes {key,label,color,axis,unit} + AXIS par courbe
// [D] HTML squelette : u-root > (u-tl placeholder) + u-scroll > section PAC (u-card info + u-grid 4 u-chart) + sections chaudiere/usage (vides, remplies Task 3/4)
// [E] setTimeout(fn, 60) : cleanup window.__tbPacUnified ; resolveDevice ; wireResponsiveGrid ; startSharedLoop
// [F] startSharedLoop : fetchShared() -> renderAll() ; setInterval 30s ; ResizeObserver
// [G] renderChart(cfg) : moteur SVG parametre (porte de _src/pac_chart_temperatures.fn.js)
// [H] buildPacInfo(flatLatest) : porte de _src/pac_info.fn.js
// return html;
```

- [ ] **Step 1 : Bloc [A] helpers** — copier *verbatim* depuis `_src/pac_chart_temperatures.fn.js` :
  - `PACV2_FLATTEN`, `PACV2_TO_SERIES` (fonctions nommées en tête du fichier),
  - dans le `setTimeout`, les fonctions `getToken`, `getTimeWindow`, `getAggInterval` (les remonter au scope module pour réutilisation).
  Aucune modification de logique. Ce sont les mêmes que dans les charts actuels.

- [ ] **Step 2 : Bloc [C] specs des 6 courbes** (reprend exactement v289-v293) :

```javascript
var P = resolveHpIndex(ctxRef); var pre = 'HP' + P + '_';
var CHARTS = [
  { id:'press', title:'Pressions HP / BP', svg:'u-svg-press',
    series:[{key:pre+'pHi',label:'Pression HP',color:'#ef5350',axis:'left',unit:' bar'},
            {key:pre+'pLo',label:'Pression BP',color:'#42a5f5',axis:'left',unit:' bar'}],
    axis:{left:{min:0,max:45},freq:{min:0,max:120},pwr:{min:0,max:30000},dpf:{min:0,max:2200}} },
  { id:'temp', title:'Températures', svg:'u-svg-temp',
    series:[{key:pre+'tIn',label:'T° entrée PAC',color:'#42a5f5',axis:'left',unit:'°C'},
            {key:pre+'tOut',label:'T° sortie PAC',color:'#ef5350',axis:'left',unit:'°C'},
            {key:'tExt',label:'T° extérieure',color:'#90a4ae',axis:'left',unit:'°C'}],
    axis:{left:{min:-30,max:90},freq:{min:0,max:120},pwr:{min:0,max:30000},dpf:{min:0,max:2200}} },
  { id:'frig', title:'Cycle frigorifique', svg:'u-svg-frig',
    series:[{key:pre+'tOH',label:'Surchauffe',color:'#fbc02d',axis:'left',unit:'°C'},
            {key:pre+'tSC',label:'Sous-refroidissement',color:'#8d6e63',axis:'left',unit:'°C'},
            {key:pre+'tEvap',label:'T° évaporation',color:'#26c6da',axis:'left',unit:'°C'},
            {key:pre+'tCond',label:'T° condensation',color:'#ff7043',axis:'left',unit:'°C'}],
    axis:{left:{min:-30,max:90},freq:{min:0,max:120},pwr:{min:0,max:30000},dpf:{min:0,max:2200}} },
  { id:'comp', title:'Compresseur / Détendeur', svg:'u-svg-comp',
    series:[{key:pre+'invert_freq',label:'Fréq compresseur',color:'#66bb6a',axis:'freq',unit:' Hz'},
            {key:pre+'invert_pwr',label:'Puiss compresseur',color:'#ab47bc',axis:'pwr',unit:' W'},
            {key:pre+'dpf',label:'Position détendeur',color:'#5c6bc0',axis:'dpf',unit:' pas'}],
    axis:{left:{min:-30,max:90},freq:{min:0,max:120},pwr:{min:0,max:30000},dpf:{min:0,max:2200}} }
];
```

  (En Task 3 on ajoutera `temp_ch` et `brul` à un tableau `CHARTS_BOIL` ; même forme.)

- [ ] **Step 3 : Bloc [G] `renderChart(cfg)` — porter le moteur** depuis `_src/pac_chart_temperatures.fn.js`.

  Transformation : le moteur actuel a `SERIES`, `AXIS`, `seriesData`, et des ids DOM fixes (`chart-svg-pac`, `chart-tooltip-pac`, `chart-legend-pac`) + un global `window.__tbChartPac`. Le convertir en fonction prenant `cfg` :
  - `var SERIES = cfg.series; var AXIS = cfg.axis;`
  - remplacer `chart-svg-pac` → `cfg.svg`, `chart-tooltip-pac` → `cfg.svg+'-tip'`, `chart-legend-pac` → `cfg.svg+'-leg'` ;
  - `seriesData` devient un paramètre : `renderChart(cfg, seriesData, win, evtIntervals)` ;
  - supprimer le `fetchSeries`/`setInterval` interne du moteur (le fetch est désormais centralisé dans `startSharedLoop`, bloc [F]) ; garder seulement `drawChart` + `drawLegend` + `smoothPath` + les helpers de dessin + `__EVT_RECTS`.
  - le state de visibilité de légende : remplacer `window.__tbChartPac.visByPrefix` par `window.__tbPacUnified.vis[cfg.id]` (scope par chart).
  Le reste (Fritsch-Carlson, axes multi-échelles, rescale pwr dynamique, ticks X/Y, tooltip) reste **inchangé**.

- [ ] **Step 4 : Bloc [F] `startSharedLoop`** (NOUVEAU, code complet) :

```javascript
function startSharedLoop() {
  var DEVICE_ID = resolveDevice();
  if (!DEVICE_ID) { console.warn('[unified] no device'); return; }
  var EVT = { intervals: [], last: 0 };
  function fetchShared() {
    var win = getTimeWindow();
    var iv = getAggInterval(win);
    var url = '/api/plugins/telemetry/DEVICE/' + DEVICE_ID +
      '/values/timeseries?keys=pac_v2&startTs=' + win.startTs + '&endTs=' + win.endTs +
      '&interval=' + iv + '&agg=NONE&limit=20000';
    fetch(url, { headers: { 'X-Authorization': 'Bearer ' + getToken() } })
      .then(function(r){ return r.json(); })
      .then(function(resp){
        var pts = resp.pac_v2 || [];
        var allKeys = []; CHARTS.concat(window.__CHARTS_BOIL||[]).forEach(function(c){ c.series.forEach(function(s){ allKeys.push(s.key); }); });
        var seriesData = PACV2_TO_SERIES({pac_v2: pts}, allKeys);
        var latestFlat = {};
        if (pts.length) { try { var raw = pts[pts.length-1].value; latestFlat = PACV2_FLATTEN(typeof raw==='string'?JSON.parse(raw):raw); } catch(e){} }
        fetchEvt(DEVICE_ID, win, EVT, function(){ renderAll(seriesData, latestFlat, win, EVT.intervals); });
        renderAll(seriesData, latestFlat, win, EVT.intervals);
      })
      .catch(function(e){ showBanner('Erreur de chargement des données.'); console.warn('[unified] fetch', e); });
  }
  fetchShared();
  window.__tbPacUnified.timer = setInterval(fetchShared, 30000);
}
function renderAll(seriesData, latestFlat, win, evt) {
  safe('pacinfo', function(){ var el=document.getElementById('u-pac-info'); if(el) el.innerHTML = buildPacInfo(latestFlat); });
  CHARTS.forEach(function(c){ safe(c.id, function(){ renderChart(c, seriesData, win, evt); }); });
  if (window.__renderBoiler) window.__renderBoiler(seriesData, latestFlat, win, evt); // Task 3
  if (window.__renderUsage)  window.__renderUsage();                                  // Task 4 (admin only)
}
function safe(tag, fn){ try { fn(); } catch(e){ var el=document.getElementById('u-err-'+tag); if(el) el.innerHTML='<div class="u-err">Section '+tag+' indisponible</div>'; console.warn('[unified]', tag, e); } }
function showBanner(msg){ var el=document.getElementById('u-banner'); if(el){ el.textContent=msg; el.style.display='block'; } }
```

- [ ] **Step 5 : Bloc [F bis] `fetchEvt`** — porter `__EVT_FETCH` de `_src/pac_chart_temperatures.fn.js` en fonction `fetchEvt(deviceId, win, EVT, cb)` (mêmes constantes FAULT_CODES/PAC_DEVICES, throttle 30 s via `EVT.last`, écrit `EVT.intervals`, appelle `cb`).

- [ ] **Step 6 : Bloc [B] (haut de fonction) + [E] `setTimeout`** (NOUVEAU, code complet).

  [B] — à placer AVANT `CHARTS` (Step 2) :
```javascript
var ctxRef = (typeof ctx!=='undefined'&&ctx)?ctx:(typeof self!=='undefined'?self.ctx:null);
function resolveHpIndex(c){ try{ var sp=c&&c.stateController?c.stateController.getStateParams():null; if(sp&&sp.hpIndex) return Number(sp.hpIndex);}catch(_){ } return 1; }
function resolveDevice(){ try{ var d=ctxRef&&ctxRef.datasources&&ctxRef.datasources[0]; if(d&&d.entityId) return d.entityId; if(d&&d.entity&&d.entity.id) return d.entity.id.id; }catch(e){} return null; }
function getToken(){ return localStorage.getItem('jwt_token'); }
var P = resolveHpIndex(ctxRef); var pre = 'HP' + P + '_';
```

  [E] — bloc setTimeout (cleanup + responsive + boucle) :
```javascript
function wireResponsiveGrid(){
  var grids = document.querySelectorAll('.u-grid');
  function apply(){ var w = (document.querySelector('.u-scroll')||{}).clientWidth || 1000;
    var cols = w < 600 ? '1fr' : '1fr 1fr';
    grids.forEach(function(g){ g.style.gridTemplateColumns = cols; }); if(window.__tbPacUnified.onResize) window.__tbPacUnified.onResize(); }
  apply();
  var ro = new ResizeObserver(apply); var sc = document.querySelector('.u-scroll'); if(sc) ro.observe(sc);
  window.__tbPacUnified.ro = ro;
}
setTimeout(function(){
  var prev = window.__tbPacUnified || {};
  if (prev.timer) clearInterval(prev.timer);
  if (prev.ro) { try{ prev.ro.disconnect(); }catch(e){} }
  window.__tbPacUnified = { vis:{} };
  wireResponsiveGrid();
  startSharedLoop();
}, 60);
```

- [ ] **Step 7 : Bloc [D] squelette HTML** (NOUVEAU) — construire `html` :

```javascript
function chartCard(c){ return '<div class="u-card u-chart" id="u-err-'+c.id+'-wrap"><div class="u-chart-title">'+c.title+'</div>'+
  '<div class="u-chart-body"><svg id="'+c.svg+'" preserveAspectRatio="xMidYMid meet"></svg>'+
  '<div id="'+c.svg+'-tip" style="display:none;position:absolute;background:rgba(0,0,0,0.75);color:#fff;padding:8px 12px;border-radius:6px;font-size:12px;pointer-events:none;z-index:10"></div></div>'+
  '<div id="'+c.svg+'-leg" class="u-chart-legend"></div><div id="u-err-'+c.id+'"></div></div>'; }
var html = '<div class="u-root">'+
  '<div id="u-banner" class="u-err" style="display:none"></div>'+
  '<div class="u-scroll">'+
    '<div class="u-tl" id="u-timeline"></div>'+                       /* rempli Task 5 */
    '<div class="u-section"><div class="u-card" id="u-pac-info"></div>'+
      '<div class="u-grid">'+CHARTS.map(chartCard).join('')+'</div></div>'+
    '<div class="u-section" id="u-boiler"></div>'+                    /* rempli Task 3 */
    '<div class="u-section" id="u-usage"></div>'+                     /* rempli Task 4 */
  '</div></div>';
return html;
```

- [ ] **Step 8 : Bloc [H] `buildPacInfo`** — porter de `_src/pac_info.fn.js` : extraire les fonctions `isBad`/`fv`/`buildValueRow` + la construction HTML des lignes info PAC (fréq, puiss, ventilateur, détendeur, surchauffe, temps). Signature : `function buildPacInfo(e){ ... return html; }` où `e` = objet flatten du dernier point. Retirer tout fetch/retroview interne (le device et le dernier point viennent de `startSharedLoop`).

- [ ] **Step 9 : `node --check`**

Run: `python -X utf8 -c "import subprocess,sys; src=open(r'scripts/tb/dashboards/_src/unified.fn.js',encoding='utf-8').read(); open('_t.js','w',encoding='utf-8').write('function f(ctx,self,data){'+src+'}'); print(subprocess.run([r'ui-ngx/target/node/node.exe','--check','_t.js'],capture_output=True,text=True).stderr or 'OK')"`
Expected : `OK`

- [ ] **Step 10 : Déployer phase 1 + vérifier en prod**

Run: `python -X utf8 scripts\tb\dashboards\deploy-unified-widget.py --pwd <pwd> --phase 1`
Vérif navigateur (le widget unifié apparaît en haut, legacy en dessous) : info PAC à jour, 4 courbes tracées, **1 seul** appel `pac_v2`/30 s (onglet réseau), légende cliquable indépendante par courbe, marqueurs evt présents, grille 2 col desktop / 1 col mobile.

- [ ] **Step 11 : Commit**

```
git add scripts/tb/dashboards/_src/unified.fn.js
git commit -m "feat(scripts/tb): widget PAC unifie - socle + section PAC (phase 1)"
```

---

## Task 3 : Section Chaudière (info + 2 courbes)

**Files:** Modify `scripts/tb/dashboards/_src/unified.fn.js`

- [ ] **Step 1 : `CHARTS_BOIL`** (après `CHARTS`) :

```javascript
var CHARTS_BOIL = [
  { id:'temp_ch', title:'Températures chaudière', svg:'u-svg-tempch',
    series:[{key:pre+'tOut',label:'T° entrée chaud.',color:'#42a5f5',axis:'left',unit:'°C'},
            {key:pre+'boil_tOut',label:'T° sortie chaud.',color:'#ef5350',axis:'left',unit:'°C'},
            {key:pre+'boil_tSmoke',label:'T° fumée',color:'#ff9800',axis:'left',unit:'°C'}],
    axis:{left:{min:-30,max:90},freq:{min:0,max:120},pwr:{min:0,max:30000},dpf:{min:0,max:2200}} },
  { id:'brul', title:'Brûleur / Circuit eau', svg:'u-svg-brul',
    series:[{key:pre+'boil_qe',label:'Débit eau',color:'#29b6f6',axis:'left',unit:' L/h'},
            {key:pre+'boil_rpm',label:'Vitesse brûleur',color:'#ff9800',axis:'freq',unit:' rpm'},
            {key:pre+'boil_press',label:'Pression eau',color:'#66bb6a',axis:'dpf',unit:' bar'}],
    axis:{left:{min:0,max:4000},freq:{min:0,max:7000},pwr:{min:0,max:30000},dpf:{min:0,max:4}} }
];
window.__CHARTS_BOIL = CHARTS_BOIL;  // pour que fetchShared collecte aussi ces cles
```

- [ ] **Step 2 : Remplir la section `#u-boiler`** dans le squelette HTML (bloc [D]) :

```javascript
// remplacer '<div class="u-section" id="u-boiler"></div>' par :
'<div class="u-section" id="u-boiler"><div class="u-card" id="u-boil-info"></div>'+
  '<div class="u-grid">'+CHARTS_BOIL.map(chartCard).join('')+'</div></div>'+
```

- [ ] **Step 3 : `buildBoilerInfo`** — porter de `_src/boiler_info.fn.js` (déjà lisible : `isBad`/`fv`/`buildValueRow`/`tH` + les deux blocs « Chaudière » et « Pompe »). Signature `function buildBoilerInfo(e){...}`. Réutiliser les `isBad`/`fv`/`buildValueRow` déjà définis pour `buildPacInfo` (DRY — ne pas redéclarer).

- [ ] **Step 4 : `window.__renderBoiler`** (appelé par `renderAll`) :

```javascript
window.__renderBoiler = function(seriesData, latestFlat, win, evt){
  safe('boilinfo', function(){ var el=document.getElementById('u-boil-info'); if(el) el.innerHTML=buildBoilerInfo(latestFlat); });
  CHARTS_BOIL.forEach(function(c){ safe(c.id, function(){ renderChart(c, seriesData, win, evt); }); });
};
```

- [ ] **Step 5 : `node --check`** (cf. Task 2 Step 9). Expected `OK`.
- [ ] **Step 6 : Déployer phase 2 + vérifier** : `deploy-unified-widget.py --pwd <pwd> --phase 2`. Vérif : section chaudière (info + 2 courbes), toujours **1 seul** fetch (les clés boil sont dans la même requête), brûleur lisible (3 échelles).
- [ ] **Step 7 : Commit** `feat(scripts/tb): widget PAC unifie - section chaudiere (phase 2)`

---

## Task 4 : Donut Usage (module autonome, gating admin, masquage rétroview)

**Files:** Modify `scripts/tb/dashboards/_src/unified.fn.js`

Le donut est **autonome** : plage propre (`localStorage tduo.usagePie.range`, défaut 30j), 3 mini-fetches, agrégation delta de compteurs. On porte le controller `usage_pie` quasi tel quel.

- [ ] **Step 1 : Porter le module donut** depuis `_src/usage_pie.controller.js`. Encapsuler tout son code (constantes COLORS/LABELS/SLICE_ORDER/PRESETS, `resolveHpIndex`, `_loadRange`/`_saveRange`/`_wirePresets`/`_applyPresetButtons`/`_refresh`, `pickPoint`/`parsePacV2`/`detectMode`/`counterToMs`/`render`/`renderSvg`/`arcPath`/`renderLegend`/`fmtDuration`/`fmtPeriod`) dans une IIFE exposant `window.__renderUsage`. Adaptations :
  - le controller utilise `self.ctx.$container` → remplacer par le conteneur `document.getElementById('u-usage')` ;
  - le device vient de `resolveDevice()` (déjà dispo) ;
  - le sélecteur de plage (PRESETS) est injecté dans `#u-usage` ;
  - **conserver** le masquage rétroview (test `sessionStorage.tduo.retroview.endTs`) et le gating admin (fetch `/api/auth/user` + attribut `is_admin`) ; si non-admin ou rétroview → `#u-usage` reste vide (ne pas rendre).
  - renommer la fonction `fmtDuration` du donut en `fmtDurUsage` pour ne pas entrer en collision avec un éventuel homonyme (le moteur de courbes n'en a pas, mais prudence).

- [ ] **Step 2 : Gate d'appel dans `renderAll`** — déjà prévu (`if (window.__renderUsage) window.__renderUsage();`). Le module décide lui-même (admin/rétroview) s'il rend. Comme le donut a sa propre plage, `__renderUsage` ne dépend pas de `seriesData` ; il peut s'auto-initialiser une fois dans le `setTimeout` plutôt qu'à chaque tick. **Décision :** appeler `__renderUsage()` une seule fois après `startSharedLoop()` (le donut gère son propre rafraîchissement via ses boutons de plage). Retirer l'appel par-tick de `renderAll` pour éviter des fetches donut à chaque tick.

- [ ] **Step 3 : CSS donut** — ajouter à `_src/unified.css` les règles `.upie-*` portées de l'ancien widget (head/title/period/presets/custom/body/svg/legend/row/swatch/lbl/pct/dur/retroview-blocked). Les recopier depuis le `settingsSchema`/CSS du widget `usage_pie` si disponibles, sinon styliser minimalement (flex, donut centré).

- [ ] **Step 4 : `node --check`**. Expected `OK`.
- [ ] **Step 5 : Déployer phase 3 + vérifier** : `--phase 3`. Vérif **en compte admin ET en compte client** : donut visible+pourcentages cohérents avec l'ancien (même plage 30j) côté admin ; **section Usage absente** côté client non-admin ; masquée en rétroview.
- [ ] **Step 6 : Commit** `feat(scripts/tb): widget PAC unifie - donut usage admin-gated (phase 3)`

---

## Task 5 : Timeline absorbée + nettoyage des widgets legacy

**Files:** Modify `scripts/tb/dashboards/_src/unified.fn.js` ; Create `scripts/tb/dashboards/retire-legacy-pac-widgets.py`

- [ ] **Step 1 : Porter la barre Timeline** depuis `_src/timeline.fn.js` dans `#u-timeline`. Injecter le HTML (boutons 4/8/12/24h + slider zoom + label) et le wiring (`getButtonH`/`getZoom`/`setButton`/`setZoom`/`fmtDuration`/`refresh`). **Différence clé :** après `setButton`/`setZoom`, en plus de `refresh()`, **déclencher un re-fetch immédiat** des courbes : appeler `window.__tbPacUnified.refetch && window.__tbPacUnified.refetch()`. Exposer `refetch` dans `startSharedLoop` : `window.__tbPacUnified.refetch = fetchShared;`. (Renommer le `fmtDuration` de la timeline en `fmtDurTl` pour éviter collision avec celui du donut.)

- [ ] **Step 2 : `node --check`**. Expected `OK`.
- [ ] **Step 3 : Déployer phase 4 + vérifier** : `--phase 4`. Vérif : la barre timeline sticky en haut du panneau pilote **immédiatement** les 6 courbes (boutons + zoom), reste collée au scroll. Le widget Timeline legacy (encore présent dessous) devient redondant — normal à ce stade.

- [ ] **Step 4 : Écrire `retire-legacy-pac-widgets.py`** — voir annexe D. Login → GET → backup → pour chaque id de `LEGACY_WIDS` : supprimer de `conf['widgets']` ET de `states['donnees_HP1'].layouts.main.widgets` (garder `WID_UNIFIED`) → repositionner `WID_UNIFIED` en plein écran (layout phase 5) → POST. Idempotent (skip si déjà absent). `--dry-run` supporté.

- [ ] **Step 5 : Dry-run du nettoyage**

Run: `python -X utf8 scripts\tb\dashboards\retire-legacy-pac-widgets.py --pwd <pwd> --dry-run`
Expected : liste des 10 widgets à retirer, `WID_UNIFIED` conservé, preview écrite, aucun POST.

- [ ] **Step 6 : Exécuter le nettoyage + vérifier** : `retire-legacy-pac-widgets.py --pwd <pwd>`. Vérif : l'état `donnees_HP1` ne contient plus **qu'un seul widget** ; toute la page est rendue par lui ; comparer visuellement avec les captures pré-fusion. Re-vérifier mobile (scroll unique, sticky, pas de capture).

- [ ] **Step 7 : Commit**

```
git add scripts/tb/dashboards/_src/unified.fn.js scripts/tb/dashboards/_src/unified.css scripts/tb/dashboards/retire-legacy-pac-widgets.py
git commit -m "feat(scripts/tb): widget PAC unifie - timeline absorbee + retrait legacy (phases 4-5)"
```

- [ ] **Step 8 : Mettre à jour la mémoire** du dashboard ([[project-dashboard-mes-installations]]) : l'état `donnees_HP1` = 1 widget unifié (ids legacy retirés, `WID_UNIFIED` = `a1b2c3d4-0700-…`).

---

## Annexes (code complet à recopier)

### Annexe A — `_lib_tb.py`

```python
#!/usr/bin/env python3
"""Helpers partages pour les scripts dashboard TB (login, GET, POST, backup)."""
import json, os, sys, time, urllib.request, urllib.error

BASE_URL     = 'https://thingsboard.tsmart.fr'
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
STATE_ID     = 'donnees_HP1'

def login(user, pwd):
    b = json.dumps({'username': user, 'password': pwd}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']

def token_or_login(user, pwd):
    t = os.environ.get('TB_TOKEN')
    if t:
        return t
    if not pwd:
        sys.exit('Fournir --pwd ou definir TB_TOKEN')
    return login(user, pwd)

def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    try:
        with urllib.request.urlopen(r, timeout=60) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'GET {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')

def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8',
                 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=300) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'POST {p} -> HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')

def get_dashboard(t):
    return http_get(f'/api/dashboard/{DASHBOARD_ID}', t)

def backup(dash, tag):
    here = os.path.dirname(os.path.abspath(__file__))
    ts = time.strftime('%Y%m%d-%H%M%S')
    path = os.path.join(here, f'backup-mes-installations.before_{tag}.{ts}.json')
    with open(path, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
    print(f'backup: {path}')
    return path

def post_dashboard(dash, t):
    resp = http_post('/api/dashboard', dash, t)
    print(f'POST OK, version dashboard: {resp.get("version", "?")}')
    return resp
```

### Annexe B — `_src/unified.css`

```css
.tb-markdown-view {
    display: flex !important; flex-direction: column !important;
    height: 100% !important; min-height: 100% !important;
    overflow: hidden !important; padding: 0 !important;
    box-sizing: border-box;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}
.tb-markdown-view *, .tb-markdown-view *:before, .tb-markdown-view *:after { box-sizing: border-box; }
.u-root { display: flex; flex-direction: column; height: 100%; min-height: 0; background: #eee; }
.u-scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: 6px; display: flex; flex-direction: column; gap: 6px; }
.u-tl { position: sticky; top: 0; z-index: 5; }
.u-section { display: flex; flex-direction: column; gap: 6px; }
.u-grid { display: grid; gap: 6px; }
.u-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; box-shadow: none; }
.u-chart { display: flex; flex-direction: column; min-height: 200px; padding: 8px; }
.u-chart-title { font-size: 13px; font-weight: 700; color: #333; text-transform: uppercase; letter-spacing: 0.5px; padding-bottom: 6px; border-bottom: 1px solid #eee; }
.u-chart-body { position: relative; flex: 1 1 auto; min-height: 180px; }
.u-chart-body svg { width: 100%; height: 100%; display: block; }
.u-chart-legend { display: flex; flex-wrap: wrap; gap: 6px; padding-top: 6px; border-top: 1px solid #eee; }
.u-chart-legend > * { font-size: 11px !important; padding: 3px 8px !important; }
.u-err { color: #b71c1c; font-size: 12px; padding: 10px; background: #ffebee; border: 1px solid #ef9a9a; border-radius: 6px; }
```

### Annexe C — `deploy-unified-widget.py`

```python
#!/usr/bin/env python3
"""Upsert le widget unifie WID_UNIFIED dans donnees_HP1 + applique le layout de phase.
Lit _src/unified.fn.js et _src/unified.css. Idempotent (ecrase toujours).
Usage: deploy-unified-widget.py --pwd <pwd> [--phase 1..5] [--dry-run]"""
import argparse, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WID_UNIFIED = 'a1b2c3d4-0700-4000-a000-000000000001'
WID_TEMPLATE = 'a1b2c3d4-0001-4000-a000-000000000001'  # PAC chart existant (clone de base)
NODE = r'c:\Projets\TB\thingsboard\ui-ngx\target\node\node.exe'
HERE = os.path.dirname(os.path.abspath(__file__))

LAYOUTS = {
    1: {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 18, 'mobileOrder': 0, 'mobileHeight': 24},
    2: {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 26, 'mobileOrder': 0, 'mobileHeight': 30},
    3: {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 32, 'mobileOrder': 0, 'mobileHeight': 36},
    4: {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 34, 'mobileOrder': 0, 'mobileHeight': 38},
    5: {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 40, 'mobileOrder': 0, 'mobileHeight': 44},
}

def node_check(fn_src):
    wrapped = 'function __t(ctx, self, data){\n' + fn_src + '\n}'
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8')
    f.write(wrapped); f.close()
    r = subprocess.run([NODE, '--check', f.name], capture_output=True, text=True)
    os.unlink(f.name)
    if r.returncode != 0:
        sys.exit('node --check ECHEC:\n' + r.stderr[:1200])
    print('  node --check OK')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--phase', type=int, default=1)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    fn = open(os.path.join(HERE, '_src', 'unified.fn.js'), encoding='utf-8').read()
    css = open(os.path.join(HERE, '_src', 'unified.css'), encoding='utf-8').read()
    node_check(fn)

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    tb.backup(dash, f'unified_p{args.phase}')
    conf = dash['configuration']

    base = json.loads(json.dumps(conf['widgets'][WID_TEMPLATE]))
    base['id'] = WID_UNIFIED
    base['config']['title'] = 'PAC Hybride (unifie)'
    base['config']['settings']['markdownTextFunction'] = fn
    base['config']['settings']['markdownCss'] = css
    conf['widgets'][WID_UNIFIED] = base

    lay = conf['states']['donnees_HP1']['layouts']['main']['widgets']
    lay[WID_UNIFIED] = dict(LAYOUTS[args.phase])
    print(f'  widget upsert + layout phase {args.phase}: {LAYOUTS[args.phase]}')

    if args.dry_run:
        prev = os.path.join(HERE, f'preview-unified-p{args.phase}.json')
        open(prev, 'wb').write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] preview: {prev}')
        return
    tb.post_dashboard(dash, t)

if __name__ == '__main__':
    main()
```

### Annexe D — `retire-legacy-pac-widgets.py`

```python
#!/usr/bin/env python3
"""Phase 5 : retire les 10 widgets legacy de donnees_HP1, ne garde que le widget unifie,
et le repositionne en plein ecran. Idempotent. Usage: --pwd <pwd> [--dry-run]"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WID_UNIFIED = 'a1b2c3d4-0700-4000-a000-000000000001'
LEGACY_WIDS = [
    '49e69aac-15bc-32c4-c32d-c474cfeffa82',
    'a1b2c3d4-0400-4000-a000-000000000001',
    'a1b2c3d4-0601-4000-a000-000000000001',
    'a1b2c3d4-0001-4000-a000-000000000001',
    'a1b2c3d4-0602-4000-a000-000000000002',
    'a1b2c3d4-0603-4000-a000-000000000003',
    'a1b2c3d4-0002-4000-a000-000000000002',
    'a1b2c3d4-0003-4000-a000-000000000003',
    'a1b2c3d4-0604-4000-a000-000000000004',
    'a1b2c3d4-9997-4000-a000-000000000097',
]
FINAL_LAYOUT = {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 40, 'mobileOrder': 0, 'mobileHeight': 44}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    tb.backup(dash, 'retire_legacy')
    conf = dash['configuration']
    lay = conf['states']['donnees_HP1']['layouts']['main']['widgets']

    if WID_UNIFIED not in lay:
        sys.exit('Widget unifie absent — lancer les phases 1-4 avant le nettoyage.')

    removed = []
    for wid in LEGACY_WIDS:
        if wid in conf['widgets']:
            del conf['widgets'][wid]; removed.append(wid)
        lay.pop(wid, None)
    lay[WID_UNIFIED] = dict(FINAL_LAYOUT)
    print(f'  retires: {len(removed)} widgets ; unifie repositionne plein ecran')

    if args.dry_run:
        here = os.path.dirname(os.path.abspath(__file__))
        prev = os.path.join(here, 'preview-retire-legacy.json')
        open(prev, 'wb').write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] preview: {prev} ; widgets restants dans l\\'etat: {list(lay.keys())}')
        return
    tb.post_dashboard(dash, t)

if __name__ == '__main__':
    main()
```

## Risques & rappels d'exécution

- **Taille fonction** ~2000 lignes : `node --check` à CHAQUE édition avant POST.
- **Backup avant chaque POST** (les helpers le font) ; rollback = re-POST du backup.
- **Single point of failure** atténué par `safe(tag, fn)` (try/catch par section) + bannière fetch.
- **Donut** : plage et fetches indépendants des courbes — ne pas le brancher sur `seriesData`.
- **`@media` interdit** dans le CSS par-widget (strippé par TB) → responsive en JS (`wireResponsiveGrid`).
- **customCss global mobile** (touch-action/overflow ajouté le 2026-06-11) : revérifier qu'il n'entre pas en conflit avec le scroll interne `.u-scroll`.
- **node** : `ui-ngx/target/node/node.exe` (pas de node dans le PATH).

