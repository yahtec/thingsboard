# Fusion page Départ chauffage en widget unique — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** Remplacer les 4 widgets de l'état `depart_chauffage` par un seul widget markdown (titre + barre timeline/rétroview + rangée [table calo gauche demi-largeur | 1 courbe chauffage droite]).

**Architecture :** Dériver `heat-unified.fn.js` de `unified.fn.js` (fusion PAC, déjà en prod) en gardant le moteur `renderChart`, le fetch séparé courbe/info, la barre timeline+rétroview, `fetchEvt`, `safe`, le responsive et le cleanup ; retirer tout le PAC-spécifique (jauges, infos PAC/chaudière, donut, 6 courbes) ; ajouter la table calorimètre + 1 spec de courbe chauffage. Namespace global `window.__tbHeatUnified` distinct. Déploiement REST, idempotent, `autoFillHeight` déjà activé sur l'état.

**Tech Stack :** ThingsBoard 4.3 markdown_card (JS vanilla, SVG inline), API REST `/api/dashboard`, Python 3 (urllib), `node --check` via `ui-ngx/target/node/node.exe`.

**Spec :** `docs/superpowers/specs/2026-06-12-heat-page-unified-widget-design.md`

## Constantes
```
DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
STATE_ID     = 'depart_chauffage'
WID_HEAT     = 'a1b2c3d4-0710-4000-a000-000000000001'   # nouveau widget unifie
WID_TEMPLATE = 'a1b2c3d4-0501-4000-a000-000000000001'   # Chauffage Chart existant (clone de base)
LEGACY_HEAT  = ['a1b2c3d4-0502-4000-a000-000000000001',  # Header
                'a1b2c3d4-0500-4000-a000-000000000001',  # Info calo
                'a1b2c3d4-0400-4000-a000-000000000002',  # Timeline
                'a1b2c3d4-0501-4000-a000-000000000001']  # Chart
NODE = r'c:\Projets\TB\thingsboard\ui-ngx\target\node\node.exe'
```

## Structure de fichiers
```
scripts/tb/dashboards/
  _src/heat-unified.fn.js     # CREE en Task 1 (derive de _src/unified.fn.js)
  _src/heat-unified.css       # CREE en Task 1 (copie de unified.css)
  deploy-heat-widget.py       # CREE en Task 1 (copie adaptee de deploy-unified-widget.py)
  retire-legacy-heat-widgets.py  # CREE en Task 2 (copie adaptee de retire-legacy-pac-widgets.py)
```
`_lib_tb.py` est réutilisé tel quel.

---

## Task 1 : Widget chauffage unifié (heat-unified.fn.js + css + deploy)

**Files:**
- Create: `scripts/tb/dashboards/_src/heat-unified.css` (copie de `_src/unified.css`)
- Create: `scripts/tb/dashboards/_src/heat-unified.fn.js` (dérivé de `_src/unified.fn.js`)
- Create: `scripts/tb/dashboards/deploy-heat-widget.py`

- [ ] **Step 1 : `heat-unified.css`** — copier `scripts/tb/dashboards/_src/unified.css` tel quel (mêmes classes `.u-root/.u-scroll/.u-tl/.u-section/.u-grid/.u-card/.u-chart*`). Aucune modif nécessaire.

- [ ] **Step 2 : Partir de `unified.fn.js`** — copier `_src/unified.fn.js` vers `_src/heat-unified.fn.js`, puis appliquer les transformations ci-dessous. RAPPEL : tout le contenu visible injecté via innerHTML doit être en **styles inline** (le CSS scopé TB ne s'y applique pas).

- [ ] **Step 3 : Renommer le namespace global** — remplacer TOUTES les occurrences de `window.__tbPacUnified` par `window.__tbHeatUnified` dans `heat-unified.fn.js` (le PAC reste sur `__tbPacUnified` ; namespaces distincts pour cohabiter). `window.__tbvPicker` (rétroview) reste partagé — ne pas renommer.

- [ ] **Step 4 : Retirer le PAC-spécifique** — supprimer de `heat-unified.fn.js` :
  - `needleAngle`, `buildGauge` (jauges) ;
  - `buildPacInfo`, `buildBoilerInfo`, `infoFrame`, `infoSub` (infos PAC/chaudière) ;
  - les tableaux `CHARTS` (6 courbes) et `CHARTS_BOIL`, et `window.__CHARTS_BOIL` ;
  - tout le module donut `window.__renderUsage` (l'IIFE complète) et son appel dans le setTimeout ;
  - garder : helpers PACV2, `getToken/resolveDevice/getTimeWindow/getAggInterval`, `P`/`pre` (inutile ici mais inoffensif — peut rester), `renderChart`, `fetchEvt`/`__EVT_RECTS`, `infoTable` (réutilisé pour la police 14/18), `safe`, `showBanner`, `wireResponsiveGrid`, `buildTimelineBar`/`wireTimelineBar` + tout le bloc rétroview `/* TBV-DETAIL */`, le `setTimeout` (cleanup), `startSharedLoop`.

- [ ] **Step 5 : Spec de la courbe chauffage** — remplacer la définition de `CHARTS` par UNE seule courbe :
```javascript
var HEAT_CHART = {
  id:'heat', title:'Chauffage', svg:'u-svg-heat',
  series:[{key:'heat_setpoint',label:'Consigne départ',color:'#7cb342',axis:'left',unit:'°C'},
          {key:'heat_tOut',    label:'T° départ chauffage',color:'#ef5350',axis:'left',unit:'°C'},
          {key:'heat_tIn',     label:'T° retour chauffage',color:'#42a5f5',axis:'left',unit:'°C'},
          {key:'tExt',         label:'T° extérieure',color:'#90a4ae',axis:'left',unit:'°C'}],
  axis:{left:{min:-20,max:90},freq:{min:0,max:120},pwr:{min:0,max:30000},dpf:{min:0,max:2200}}
};
```

- [ ] **Step 6 : Table calorimètre** — ajouter `CALO_UNITS` + `caloInfo(e)` (porté de `_src/heat_info_calo.fn.js`, en styles inline, police 14/18 comme PAC). Réutiliser `fv`/`isBad` déjà présents.
```javascript
var CALO_UNITS = {
  2875:{m:1,u:'L/h',d:0}, 2860:{m:10,u:'W',d:0}, 3092:{m:0.01,u:'m³',d:2},
  3093:{m:0.1,u:'m³',d:1}, 3078:{m:1,u:'kWh',d:0}, 3079:{m:10,u:'kWh',d:0}
};
function caloRowHtml(label, val, unit, uVal){
  var disp, udisp=''; var n=Number(uVal); if(isNaN(n)) n=parseInt(String(uVal),16);
  var spec = n ? CALO_UNITS[n] : null;
  if(spec){ var v=parseFloat(val); disp = isBad(v) ? '--' : (v*spec.m).toFixed(spec.d); udisp=spec.u; }
  else { disp = fv(val, unit||'', 1); if(n) udisp='u:0x'+n.toString(16).toUpperCase(); }
  return '<tr>'+
    '<td style="font-size:14px;color:#666;text-transform:uppercase;letter-spacing:0.3px;padding:5px 8px 5px 0;border-bottom:1px solid #eee">'+label+'</td>'+
    '<td style="font-size:18px;font-weight:bold;color:#222;text-align:right;white-space:nowrap;padding:5px 8px;border-bottom:1px solid #eee">'+disp+'</td>'+
    '<td style="font-size:14px;color:#888;padding:5px 0;border-bottom:1px solid #eee">'+udisp+'</td>'+
    '</tr>';
}
function caloInfo(e){
  e = e || {};
  var rows =
    caloRowHtml('Puissance', e['heat_calo_pwr'], '', e['heat_calo_pwrU'])+
    caloRowHtml('Énergie chauffage', e['heat_calo_hKwh'], '', e['heat_calo_hKwhU'])+
    caloRowHtml('Énergie refroidissement', e['heat_calo_cKwh'], '', e['heat_calo_cKwhU'])+
    caloRowHtml('Débit', e['heat_calo_qe'], '', e['heat_calo_qeU'])+
    caloRowHtml('Volume total', e['heat_calo_qeTot'], '', e['heat_calo_qeTotU'])+
    caloRowHtml('T° aller', e['heat_calo_tIn'], ' °C')+
    caloRowHtml('T° retour', e['heat_calo_tRet'], ' °C');
  return '<div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#333;padding-bottom:6px;border-bottom:1px solid #e0e0e0;margin-bottom:8px">Calorimètre chauffage</div>'+
    '<table style="width:100%;border-collapse:collapse"><tbody>'+rows+'</tbody></table>';
}
```

- [ ] **Step 7 : `renderCharts` / `renderInfo`** — remplacer les versions PAC par :
```javascript
function renderCharts(seriesData, win, evt){
  safe('heat', function(){ renderChart(HEAT_CHART, seriesData, win, evt); });
}
function renderInfo(latestFlat){
  safe('caloinfo', function(){ var el=document.getElementById('u-calo'); if(el) el.innerHTML=caloInfo(latestFlat); });
}
```
Dans `fetchCharts`, la collecte de clés devient : `var allKeys=[]; HEAT_CHART.series.forEach(function(s){ allKeys.push(s.key); });` (retirer la référence à `CHARTS`/`window.__CHARTS_BOIL`). `fetchInfo` inchangé (latest → renderInfo). Retirer l'appel `window.__renderUsage()` du setTimeout.

- [ ] **Step 8 : Squelette HTML** — remplacer la construction de `html` par titre + timeline + rangée [calo gauche | courbe droite] :
```javascript
function chartCard(c){ return '<div class="u-card u-chart" style="flex:1 1 320px;min-width:280px"><div class="u-chart-title">'+c.title+'</div>'+
  '<div class="u-chart-body"><svg id="'+c.svg+'" preserveAspectRatio="xMidYMid meet"></svg>'+
  '<div id="'+c.svg+'-tip" style="display:none;position:absolute;background:rgba(0,0,0,0.75);color:#fff;padding:8px 12px;border-radius:6px;font-size:12px;pointer-events:none;z-index:10"></div></div>'+
  '<div id="'+c.svg+'-leg" class="u-chart-legend"></div><div id="u-err-'+c.id+'"></div></div>'; }
var html = '<div class="u-root">'+
  '<div id="u-banner" class="u-err" style="display:none"></div>'+
  '<div class="u-scroll">'+
    '<div style="font-size:16px;font-weight:700;color:#333;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px">Départ chauffage</div>'+
    '<div class="u-tl" id="u-timeline">'+buildTimelineBar()+'</div>'+
    '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start">'+
      '<div class="u-card" style="flex:1 1 320px;min-width:280px;max-width:480px;padding:12px 14px"><div id="u-calo"></div><div id="u-err-caloinfo"></div></div>'+
      chartCard(HEAT_CHART)+
    '</div>'+
  '</div></div>';
```
Note : la rangée flex donne [calo gauche demi-largeur | courbe droite] en desktop, et empile en mobile (wrap). `wireResponsiveGrid` n'a plus de `.u-grid` à piloter — sans effet, inoffensif (le flex-wrap suffit). On peut laisser `wireResponsiveGrid` tel quel.

- [ ] **Step 9 : `node --check`**
Run: `python -c "import subprocess; open('_t.js','w',encoding='utf-8').write('function f(ctx,self,data){'+open(r'scripts/tb/dashboards/_src/heat-unified.fn.js',encoding='utf-8').read()+'}'); r=subprocess.run([r'ui-ngx/target/node/node.exe','--check','_t.js'],capture_output=True,text=True); print(r.stderr or 'JS OK')"` puis supprimer `_t.js`.
Expected : `JS OK`. Itérer jusqu'à passage. Vérifier : aucune ref restante à `buildGauge`/`buildPacInfo`/`buildBoilerInfo`/`CHARTS_BOIL`/`__renderUsage`/`__tbPacUnified` ; `renderChart`/`fv`/`isBad`/`buildTimelineBar` déclarés une fois ; `return html;` en dernier.

- [ ] **Step 10 : `deploy-heat-widget.py`** — copier `deploy-unified-widget.py` et adapter : `WID=WID_HEAT`, `WID_TEMPLATE=a1b2c3d4-0501-…`, `STATE='depart_chauffage'`, lit `heat-unified.fn.js`/`heat-unified.css`, un seul layout `{'col':0,'row':0,'sizeX':24,'sizeY':24,'mobileOrder':0,'mobileHeight':28}` (autoFillHeight déjà activé). Garde : `node_check`, update-in-place si `WID_HEAT` existe sinon clone template, backup, pousse les autres widgets de l'état sous row 100 (idempotent `row<100 -> row%100+100`), `--dry-run`.

- [ ] **Step 11 : Déployer + vérifier**
Run: `python -X utf8 scripts\tb\dashboards\deploy-heat-widget.py --pwd <pwd>`
Vérif navigateur : widget unifié en haut (4 legacy poussés dessous) ; titre « Départ chauffage » ; barre timeline (zoom inversé 100% gauche/5% droite) + rétroview ; rangée [table calo gauche, police 14/18, unités Mainone | courbe à droite] ; timeline recadre la courbe ; calo = dernière valeur ; mobile empile + scroll unique.

- [ ] **Step 12 : Commit**
```
git add scripts/tb/dashboards/_src/heat-unified.fn.js scripts/tb/dashboards/_src/heat-unified.css scripts/tb/dashboards/deploy-heat-widget.py
git commit -m "feat(scripts/tb): widget chauffage unifie - calo + courbe (phase 1)"
```
(message via `git commit -F` fichier temp si multi-ligne ; trailing `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`)

---

## Task 2 : Retrait des 4 widgets legacy

**Files:** Create `scripts/tb/dashboards/retire-legacy-heat-widgets.py`

- [ ] **Step 1 : Écrire `retire-legacy-heat-widgets.py`** — copie de `retire-legacy-pac-widgets.py` adaptée : `WID_KEEP=WID_HEAT`, `LEGACY=LEGACY_HEAT` (les 4 ids ci-dessus), `STATE='depart_chauffage'`, layout final `{'col':0,'row':0,'sizeX':24,'sizeY':24,'mobileOrder':0,'mobileHeight':28}`. Supprime chaque legacy de `conf['widgets']` ET du layout, garde `WID_HEAT`, backup, `--dry-run`. Garde-fou : exit si `WID_HEAT` absent du layout.

- [ ] **Step 2 : Dry-run**
Run: `python -X utf8 scripts\tb\dashboards\retire-legacy-heat-widgets.py --pwd <pwd> --dry-run`
Expected : 4 widgets listés à retirer, `WID_HEAT` conservé, aucun POST.

- [ ] **Step 3 : Exécuter + vérifier**
Run: `python -X utf8 scripts\tb\dashboards\retire-legacy-heat-widgets.py --pwd <pwd>`
Vérif : l'état `depart_chauffage` ne contient plus qu'`a1b2c3d4-0710-…` ; rendu identique sans les legacy ; mobile OK.

- [ ] **Step 4 : Commit + push**
```
git add scripts/tb/dashboards/retire-legacy-heat-widgets.py
git commit -m "feat(scripts/tb): widget chauffage unifie - retrait des 4 legacy (phase 2)"
git push origin yahtec-main
```

- [ ] **Step 5 : Mémoire** — mettre à jour `[[project-dashboard-mes-installations]]` : `depart_chauffage` = 1 widget unifié `0710` (source `_src/heat-unified.fn.js`), legacy 0502/0500/0400-…-0002/0501 retirés.

---

## Risques & rappels
- `node --check` avant CHAQUE POST ; backup auto avant POST ; rollback = re-POST du backup.
- Globals : `window.__tbHeatUnified` distinct de `__tbPacUnified` ; `__tbvPicker` partagé (OK, une page à la fois).
- `autoFillHeight` déjà activé sur `depart_chauffage` → widget remplit le viewport, scroll unique (ne pas le re-désactiver).
- Styles inline obligatoires pour le contenu injecté (CSS scopé TB inopérant).
- node : `ui-ngx/target/node/node.exe` (pas dans le PATH).
