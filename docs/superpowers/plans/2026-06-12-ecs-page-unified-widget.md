# Page ECS (état `ecs` + widget unifié) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Page « Eau chaude sanitaire » dans le dashboard Mes Installations : timeline T° ECS (+ V3V / T° entrée module si type 3) + tableaux pompes, accessible depuis la carte Module ECS.

**Architecture:** Clone du pattern heat-unified : un état `ecs` avec UN SEUL widget markdown (`a1b2c3d4-0720-4000-a000-000000000001`), source `_src/ecs-unified.fn.js` dérivée de `_src/heat-unified.fn.js` (943 lignes) par remplacements ciblés. Déploiement REST pur via `deploy-ecs-widget.py` (état + widget) et `patch-ecs-nav-card.py` (carte cliquable). Spec : `docs/superpowers/specs/2026-06-12-ecs-page-unified-widget-design.md`.

**Tech Stack:** JS widget markdown TB (ES5, pas de framework), Python 3 stdlib + `scripts/tb/dashboards/_lib_tb.py`, node `--check` pour valider la syntaxe JS, API REST TB.

**Pré-requis exécution :** mot de passe TB (`--pwd`) ; node présent à `c:\Projets\TB\thingsboard\ui-ngx\target\node\node.exe`.

**Fait établi (prod, 2026-06-12) :** `pac_v2.type` ∈ {0,1,2,3} (0 sans module, 1 chauffage, 2 ECS seul, 3 chauffage+ECS) ; parc actuel = 0/1 uniquement. Bloc `dhw{tIn,tOut,tSet,tTank,posV3V,pump1..4{dP,pwr,qe,rpm,time}}`, pompes module `pump1M/pump2M`, T° entrée module `tInM` (2610000001, 2623001001) **ou** `TinM` (2602000001, 2602000002).

---

### Task 1 : Créer `_src/ecs-unified.fn.js` + `_src/ecs-unified.css`

**Files:**
- Create: `scripts/tb/dashboards/_src/ecs-unified.fn.js` (copie transformée de `_src/heat-unified.fn.js`)
- Create: `scripts/tb/dashboards/_src/ecs-unified.css` (copie de `_src/heat-unified.css`, inchangée)

Pas de harness JS : la validation = `node --check` (Step 8) + vérifications grep (Step 7).

- [ ] **Step 1 : Copier les fichiers**

```powershell
Copy-Item scripts/tb/dashboards/_src/heat-unified.fn.js scripts/tb/dashboards/_src/ecs-unified.fn.js
Copy-Item scripts/tb/dashboards/_src/heat-unified.css scripts/tb/dashboards/_src/ecs-unified.css
```

- [ ] **Step 2 : Renommer le namespace (remplacement global dans ecs-unified.fn.js)**

Dans `ecs-unified.fn.js` UNIQUEMENT, remplacer **toutes** les occurrences :
- `__tbHeatUnified` → `__tbEcsUnified` (≈12 occurrences)
- `__tbUnifiedRetroWired` → `__tbEcsRetroWired` (2 occurrences — listener retroview séparé par page)
- en tête de fichier, remplacer la 1re ligne `// __PAC_UNIFIED_V1__` par `// __ECS_UNIFIED_V1__`

- [ ] **Step 3 : Remplacer le bloc chart spec (section [C])**

Remplacer le bloc complet (de `var HEAT_CHART = {` à son `};` inclus, lignes ~127–134) par :

```js
var MODULE_TYPE = null; // pac_v2.type : 0 sans module, 1 chauffage seul, 2 ECS seul, 3 chauffage+ECS
var ECS_BASE_SERIES = [
  {key:'dhw_tOut',   label:'T° sortie',         color:'#ef5350', axis:'left', unit:'°C'},
  {key:'dhw_tIn',    label:'T° entrée',         color:'#42a5f5', axis:'left', unit:'°C'},
  {key:'dhw_tTank',  label:'T° ballon',         color:'#ff9800', axis:'left', unit:'°C'},
  {key:'dhw_posV3V', label:'Position V3V',      color:'#8e24aa', axis:'freq', unit:'%'},
  {key:'__tInM',     label:'T° entrée module',  color:'#26a69a', axis:'left', unit:'°C'}
];
var ECS_CHART = {
  id:'ecs', title:'ECS', svg:'u-svg-ecs',
  series: ECS_BASE_SERIES,
  // axe 'freq' detourne pour la V3V (0-100 %) ; pwr/dpf requis par le moteur (formatters) mais inutilises
  axis:{left:{min:0,max:90},freq:{min:0,max:100},pwr:{min:0,max:30000},dpf:{min:0,max:2200}}
};
function activeEcsChart(){
  var s = (MODULE_TYPE === 3) ? ECS_BASE_SERIES.slice()
        : ECS_BASE_SERIES.filter(function(x){ return x.key !== 'dhw_posV3V' && x.key !== '__tInM'; });
  return { id:ECS_CHART.id, title:ECS_CHART.title, svg:ECS_CHART.svg, series:s, axis:ECS_CHART.axis };
}
```

Notes moteur (ne PAS modifier le moteur renderChart) : `showAxes=false` → pas de labels d'axe rendus, le détournement de l'axe `freq` est purement une échelle 0–100 ; le bloc « échelle pwr dynamique » lit `pre+'invert_pwr'` absent des données → inoffensif ; les séries `axis:'left'` entièrement nulles sont auto-masquées par le moteur (check `anyReal`).

- [ ] **Step 4 : Remplacer le squelette HTML (section [D], bloc `var html = ...`)**

Remplacer le bloc complet (de `var html = '<div class="u-root">'+` à `'</div></div>';` inclus, lignes ~217–226) par :

```js
var html = '<div class="u-root">'+
  '<div id="u-banner" class="u-err" style="display:none"></div>'+
  '<div class="u-scroll">'+
    '<div style="font-size:16px;font-weight:700;color:#333;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px">Eau chaude sanitaire</div>'+
    '<div class="u-tl" id="u-timeline">'+buildTimelineBar()+'</div>'+
    '<div id="u-chartwrap" style="display:flex;flex-direction:column;height:528px">'+chartCard(ECS_CHART)+'</div>'+
    '<div class="u-grid" id="u-pumps" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px"></div>'+
  '</div></div>';
```

(`.u-grid` est déjà géré par `wireResponsiveGrid` : 1 colonne sous 600 px.)

- [ ] **Step 5 : Remplacer la section [F] (startSharedLoop / renderCharts / renderInfo)**

Remplacer le bloc complet de `function startSharedLoop() {` jusqu'à la fin de `function renderInfo(latestFlat) { ... }` inclus (lignes ~559–608 ; s'arrêter AVANT `function safe(tag, fn)`) par :

```js
function startSharedLoop() {
  var DEVICE_ID = resolveDevice();
  if (!DEVICE_ID) { console.warn('[ecs] no device'); return; }
  var EVT = { intervals: [], last: 0 };

  function infoEndTs(){ var rv = sessionStorage.getItem('tduo.retroview.endTs'); var t = rv ? parseInt(rv,10) : 0; return (t>0) ? t : Date.now(); }

  function fetchCharts() {
    var win = getTimeWindow();
    var iv = getAggInterval(win);
    var allKeys = ['dhw_tOut','dhw_tIn','dhw_tTank','dhw_posV3V','tInM','TinM'];
    var url = '/api/plugins/telemetry/DEVICE/' + DEVICE_ID +
      '/values/timeseries?keys=pac_v2&startTs=' + win.startTs + '&endTs=' + win.endTs +
      '&interval=' + iv + '&agg=NONE&limit=20000';
    fetch(url, { headers: { 'X-Authorization': 'Bearer ' + getToken() } })
      .then(function(r){ return r.json(); })
      .then(function(resp){
        var seriesData = PACV2_TO_SERIES({pac_v2: resp.pac_v2 || []}, allKeys);
        // tInM/TinM : deux casses sur le parc -> fusion vers la cle de serie __tInM
        seriesData.__tInM = (seriesData.tInM && seriesData.tInM.length) ? seriesData.tInM : (seriesData.TinM || []);
        // T° ballon : ne tracer que les valeurs plausibles [5..90] degC (spec)
        seriesData.dhw_tTank = (seriesData.dhw_tTank || []).filter(function(p){
          var v = parseFloat(p.value); return !isNaN(v) && v >= 5 && v <= 90;
        });
        fetchEvt(DEVICE_ID, win, EVT, function(){ renderCharts(seriesData, win, EVT.intervals); });
        renderCharts(seriesData, win, EVT.intervals);
      })
      .catch(function(e){ showBanner('Erreur de chargement des courbes.'); console.warn('[ecs] fetchCharts', e); });
  }

  function fetchInfo() {
    var endTs = infoEndTs();
    var url = '/api/plugins/telemetry/DEVICE/' + DEVICE_ID +
      '/values/timeseries?keys=pac_v2&startTs=0&endTs=' + endTs + '&limit=1&orderBy=DESC&agg=NONE';
    fetch(url, { headers: { 'X-Authorization': 'Bearer ' + getToken() } })
      .then(function(r){ return r.json(); })
      .then(function(resp){
        var pts = resp.pac_v2 || [];
        var latestFlat = {};
        if (pts.length) { try { var raw = pts[0].value; latestFlat = PACV2_FLATTEN(typeof raw==='string'?JSON.parse(raw):raw); } catch(e){} }
        var t = parseInt(latestFlat['type']);
        MODULE_TYPE = isNaN(t) ? null : t;
        renderInfo(latestFlat);
      })
      .catch(function(e){ console.warn('[ecs] fetchInfo', e); });
  }

  window.__tbEcsUnified.refetch = fetchCharts;                 // timeline change -> curves ONLY
  window.__tbEcsUnified.refetchAll = function(){ fetchInfo(); fetchCharts(); };
  fetchInfo(); fetchCharts();
  window.__tbEcsUnified.timer = setInterval(function(){ fetchInfo(); fetchCharts(); }, 30000);
}
function renderCharts(seriesData, win, evt) {
  safe('ecs', function(){ renderChart(activeEcsChart(), seriesData, win, evt); });
}
function renderInfo(latestFlat) {
  safe('pumps', function(){
    var el = document.getElementById('u-pumps');
    var ch = document.getElementById('u-chartwrap');
    if (!el) return;
    if (MODULE_TYPE === 0 || MODULE_TYPE === 1) {
      // garde spec : pas de module ECS sur cette installation
      if (ch) ch.style.display = 'none';
      el.innerHTML = '<div class="u-card" style="grid-column:1/-1;padding:24px;text-align:center;color:#888;font-size:14px">Pas de module ECS sur cette installation</div>';
      return;
    }
    if (ch) ch.style.display = 'flex';
    el.innerHTML = pumpsInfo(latestFlat);
  });
}
```

(NB : le namespace est déjà `__tbEcsUnified` partout grâce au Step 2 — ce bloc l'utilise directement.)

- [ ] **Step 6 : Remplacer la section calorimètre (fin de fichier) par les tableaux pompes**

Remplacer le bloc complet de `var CALO_UNITS = {` jusqu'à la fin de `function caloInfo(e){ ... }` inclus (lignes ~959–986 ; s'arrêter AVANT le `return html;` final) par :

```js
var PUMP_FIELDS = [
  ['ΔP',              'dP',   ' bar',    1],
  ['Puissance',       'pwr',  ' W',      0],
  ['Débit',           'qe',   ' m³/h',   1],
  ['Vitesse',         'rpm',  ' tr/min', 0],
  ['Temps de marche', 'time', ' h',      0]
];
function pumpPresent(e, pfx) {
  // Provisoire (spec) : un des 5 champs non nul dans le dernier pac_v2 recu
  // (time cumulatif => une pompe ayant deja tourne reste detectee a l'arret).
  // Sera remplace par les cles de presence automate (futurs ATTRIBUTS device).
  for (var i = 0; i < PUMP_FIELDS.length; i++) {
    var v = parseFloat(e[pfx + PUMP_FIELDS[i][1]]);
    if (!isNaN(v) && v !== 0) return true;
  }
  return false;
}
function pumpTable(title, e, pfx) {
  var rows = '';
  PUMP_FIELDS.forEach(function(f){
    rows += '<tr>'+
      '<td style="font-size:14px;color:#666;text-transform:uppercase;letter-spacing:0.3px;padding:5px 8px 5px 0;border-bottom:1px solid #eee">'+f[0]+'</td>'+
      '<td style="font-size:18px;font-weight:bold;color:#222;text-align:right;white-space:nowrap;padding:5px 0;border-bottom:1px solid #eee">'+fv(e[pfx+f[1]], f[2], f[3])+'</td>'+
      '</tr>';
  });
  return '<div class="u-card" style="padding:12px 14px">'+
    '<div style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#333;padding-bottom:6px;border-bottom:1px solid #e0e0e0;margin-bottom:8px">'+title+'</div>'+
    '<table style="width:100%;border-collapse:collapse"><tbody>'+rows+'</tbody></table></div>';
}
function pumpsInfo(e) {
  e = e || {};
  // type 2 (ECS seul) : pompes module a la place des primaires echangeur (spec)
  var prim = (MODULE_TYPE === 2)
    ? [['Pompe 1 module', 'pump1M_'], ['Pompe 2 module', 'pump2M_']]
    : [['Pompe primaire échangeur 1', 'dhw_pump1_'], ['Pompe primaire échangeur 2', 'dhw_pump2_']];
  var sec = [['Pompe secondaire échangeur 1', 'dhw_pump3_'], ['Pompe secondaire échangeur 2', 'dhw_pump4_']];
  var h = '';
  h += pumpTable(prim[0][0], e, prim[0][1]);
  if (pumpPresent(e, prim[1][1])) h += pumpTable(prim[1][0], e, prim[1][1]);
  h += pumpTable(sec[0][0], e, sec[0][1]);
  if (pumpPresent(e, sec[1][1])) h += pumpTable(sec[1][0], e, sec[1][1]);
  return h;
}
```

- [ ] **Step 7 : Vérifications grep**

```powershell
# plus aucune reference chauffage residuelle dans le fichier ECS :
Select-String -Path scripts/tb/dashboards/_src/ecs-unified.fn.js -Pattern 'HEAT_CHART|caloInfo|CALO_UNITS|u-calo|__tbHeatUnified|Départ chauffage' | Measure-Object | Select-Object -ExpandProperty Count
```
Expected: `0`. (Le mot `heat_calo` ne doit plus apparaître non plus ; `pre+'invert_pwr'` dans le moteur est OK.)

```powershell
Select-String -Path scripts/tb/dashboards/_src/ecs-unified.fn.js -Pattern '__tbEcsUnified' | Measure-Object | Select-Object -ExpandProperty Count
```
Expected: ≥ 10.

- [ ] **Step 8 : node --check**

```powershell
$fn = Get-Content scripts/tb/dashboards/_src/ecs-unified.fn.js -Raw
"function __t(ctx, self, data){`n$fn`n}" | Out-File -Encoding utf8 $env:TEMP\ecs_check.js
& "c:\Projets\TB\thingsboard\ui-ngx\target\node\node.exe" --check $env:TEMP\ecs_check.js
Remove-Item $env:TEMP\ecs_check.js -Confirm:$false
```
Expected: exit 0, aucune sortie d'erreur.

- [ ] **Step 9 : Commit**

```powershell
git add scripts/tb/dashboards/_src/ecs-unified.fn.js scripts/tb/dashboards/_src/ecs-unified.css
git commit -m "feat(scripts/tb): source widget ECS unifie (timeline + tableaux pompes)"
```

---

### Task 2 : Script `deploy-ecs-widget.py` (état + widget)

**Files:**
- Create: `scripts/tb/dashboards/deploy-ecs-widget.py`

- [ ] **Step 1 : Créer le script (contenu exact)**

```python
#!/usr/bin/env python3
"""Cree l'etat 'ecs' (si absent) + upsert le widget ECS unifie WID_ECS et son layout.
Lit _src/ecs-unified.fn.js et _src/ecs-unified.css. Idempotent.
Usage: deploy-ecs-widget.py --pwd <pwd> [--dry-run]"""
import argparse, copy, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

STATE = 'ecs'
GRID_TEMPLATE_STATE = 'depart_chauffage'
WID_ECS = 'a1b2c3d4-0720-4000-a000-000000000001'
WID_TEMPLATE = 'a1b2c3d4-0710-4000-a000-000000000001'  # widget chauffage unifie (clone de base)
NODE = r'c:\Projets\TB\thingsboard\ui-ngx\target\node\node.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT = {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 24, 'mobileOrder': 0, 'mobileHeight': 28}


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
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    fn = open(os.path.join(HERE, '_src', 'ecs-unified.fn.js'), encoding='utf-8').read()
    css = open(os.path.join(HERE, '_src', 'ecs-unified.css'), encoding='utf-8').read()
    node_check(fn)

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    tb.backup(dash, 'ecs_state')
    conf = dash['configuration']
    states = conf['states']

    if STATE in states:
        print(f"  [state] '{STATE}' existe deja")
    else:
        grid = copy.deepcopy(states[GRID_TEMPLATE_STATE]['layouts']['main'].get('gridSettings', {}))
        states[STATE] = {'name': 'Eau chaude sanitaire', 'root': False,
                         'layouts': {'main': {'widgets': {}, 'gridSettings': grid}}}
        print(f"  [state] '{STATE}' cree (grid clone de {GRID_TEMPLATE_STATE})")

    if WID_ECS in conf['widgets']:
        base = conf['widgets'][WID_ECS]
    elif WID_TEMPLATE in conf['widgets']:
        base = json.loads(json.dumps(conf['widgets'][WID_TEMPLATE]))
        base['id'] = WID_ECS
    else:
        sys.exit('Ni widget ECS ni template chauffage unifie present — etat inattendu.')
    base['config']['title'] = 'ECS (unifie)'
    base['config']['settings']['markdownTextFunction'] = fn
    base['config']['settings']['markdownCss'] = css
    conf['widgets'][WID_ECS] = base

    # un seul widget sur l'etat (leçon autoFillHeight : jamais de cohabitation)
    states[STATE]['layouts']['main']['widgets'] = {WID_ECS: dict(LAYOUT)}
    print(f'  widget upsert + layout {LAYOUT}')

    if args.dry_run:
        prev = os.path.join(HERE, 'preview-ecs-unified.json')
        open(prev, 'wb').write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] preview: {prev}')
        return
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2 : Vérifier la syntaxe Python**

```powershell
python -m py_compile scripts/tb/dashboards/deploy-ecs-widget.py
```
Expected: exit 0.

- [ ] **Step 3 : Commit**

```powershell
git add scripts/tb/dashboards/deploy-ecs-widget.py
git commit -m "feat(scripts/tb): deploy-ecs-widget - etat ecs + widget unifie"
```

---

### Task 3 : Script `patch-ecs-nav-card.py` (carte Module ECS cliquable)

**Files:**
- Create: `scripts/tb/dashboards/patch-ecs-nav-card.py`

Cible : widget « Données générales » `a1b2c3d4-d600-4000-a000-000000000001` (état `default`). Les anchors ci-dessous proviennent du markdown live (vérifié 2026-06-12 ; le patch `__HEATNAV_V1__` y est déjà appliqué).

- [ ] **Step 1 : Créer le script (contenu exact)**

```python
#!/usr/bin/env python3
"""Rend la carte 'Module ECS' du widget Donnees generales (etat default)
cliquable -> goState('ecs'), UNIQUEMENT si pac_v2.type vaut 2 ou 3.
Idempotent : marker __ECSNAV_V1__.
Usage: patch-ecs-nav-card.py --pwd <pwd> [--dry-run]"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WID_UNITE = 'a1b2c3d4-d600-4000-a000-000000000001'
MARKER = '__ECSNAV_V1__'


def must_replace(s, old, new, label, count=1):
    n = s.count(old)
    if n != count:
        sys.exit(f'[{label}] anchor trouve {n} fois (attendu {count}) : {old[:80]!r}')
    return s.replace(old, new, count)


OLD_OPEN = """function buildECS(e) {
    var h = '';
    h += '<div class="bloc ecs-bloc">';"""
NEW_OPEN = """function buildECS(e) {
    var h = '';
    // """ + MARKER + """ : carte cliquable si module ECS present (type 2 ou 3)
    var _t = parseInt(e['type'] || 0);
    var _nav = (_t === 2 || _t === 3);
    h += '<div class="bloc ecs-bloc"' + (_nav ? ' data-ecsnav="1" role="button" tabindex="0" aria-label="Voir ECS"' : '') + '>';"""

OLD_CLOSE = """    h += row('Consigne', fv(e['dhw_tSet'], ' C'));
    h += '</div></div>';
    return h;
}"""
NEW_CLOSE = """    h += row('Consigne', fv(e['dhw_tSet'], ' C'));
    if (_nav) h += '<div class="detail-link">Voir détails →</div>';
    h += '</div></div>';
    return h;
}"""

OLD_CLICK = """        var hb = t.closest('.heat-bloc[data-heatnav]');"""
NEW_CLICK = """        var eb = t.closest('.ecs-bloc[data-ecsnav]');
        if (eb) { ev.preventDefault(); goState('ecs'); return; }
        var hb = t.closest('.heat-bloc[data-heatnav]');"""

OLD_KEY = """        if (t.classList.contains('heat-bloc')) { ev.preventDefault(); goState('depart_chauffage'); return; }"""
NEW_KEY = """        if (t.classList.contains('ecs-bloc') && t.hasAttribute('data-ecsnav')) { ev.preventDefault(); goState('ecs'); return; }
        if (t.classList.contains('heat-bloc')) { ev.preventDefault(); goState('depart_chauffage'); return; }"""

CSS_EXTRA = """
/* __ECSNAV_CSS__ */
.ecs-bloc[data-ecsnav] { cursor: pointer; transition: box-shadow 0.2s, transform 0.15s; -webkit-tap-highlight-color: rgba(198, 40, 40, 0.15); }
.ecs-bloc[data-ecsnav]:hover { box-shadow: 0 4px 16px rgba(198, 40, 40, 0.25); transform: translateY(-2px); }
.ecs-bloc[data-ecsnav]:active { transform: translateY(0); box-shadow: 0 1px 4px rgba(198, 40, 40, 0.35); }
.ecs-bloc[data-ecsnav]:focus-visible { outline: 2px solid #c62828; outline-offset: 2px; }
.ecs-bloc[data-ecsnav] .detail-link { color: #c62828; }
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    conf = dash['configuration']
    if WID_UNITE not in conf['widgets']:
        sys.exit(f'widget Donnees generales absent : {WID_UNITE}')
    c = conf['widgets'][WID_UNITE]['config']
    fn = c['settings']['markdownTextFunction']
    if MARKER in fn:
        print('  Already patched (idempotent skip)')
        return

    fn = must_replace(fn, OLD_OPEN, NEW_OPEN, 'ecs-bloc open')
    fn = must_replace(fn, OLD_CLOSE, NEW_CLOSE, 'ecs-bloc close')
    fn = must_replace(fn, OLD_CLICK, NEW_CLICK, 'click handler')
    fn = must_replace(fn, OLD_KEY, NEW_KEY, 'keydown handler')

    if args.dry_run:
        print('DRY-RUN: 4 remplacements OK. No POST.')
        return

    tb.backup(dash, 'ecsnav')
    c['settings']['markdownTextFunction'] = fn
    c['settings']['markdownCss'] = c['settings'].get('markdownCss', '') + CSS_EXTRA
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()
```

- [ ] **Step 2 : Vérifier la syntaxe Python**

```powershell
python -m py_compile scripts/tb/dashboards/patch-ecs-nav-card.py
```
Expected: exit 0.

- [ ] **Step 3 : Commit**

```powershell
git add scripts/tb/dashboards/patch-ecs-nav-card.py
git commit -m "feat(scripts/tb): patch-ecs-nav-card - carte Module ECS cliquable si type 2/3"
```

---

### Task 4 : Déploiement prod

**Files:** aucun nouveau (backups auto, gitignorés).

- [ ] **Step 1 : Dry-run des deux scripts**

```powershell
python scripts/tb/dashboards/deploy-ecs-widget.py --pwd <PWD> --dry-run
python scripts/tb/dashboards/patch-ecs-nav-card.py --pwd <PWD> --dry-run
```
Expected : `node --check OK`, `[state] 'ecs' cree...`, `[dry-run] preview: ...preview-ecs-unified.json` ; puis `DRY-RUN: 4 remplacements OK`. Si un anchor du patch nav n'est pas trouvé : GET le widget live, comparer le bloc réel (espaces/accents), ajuster OLD_* et re-committer.

- [ ] **Step 2 : Appliquer**

```powershell
python scripts/tb/dashboards/deploy-ecs-widget.py --pwd <PWD>
python scripts/tb/dashboards/patch-ecs-nav-card.py --pwd <PWD>
```
Expected : 2 × `POST OK, version dashboard: <N>` (version +1 à chaque POST).

- [ ] **Step 3 : Vérifier l'idempotence**

```powershell
python scripts/tb/dashboards/deploy-ecs-widget.py --pwd <PWD>
python scripts/tb/dashboards/patch-ecs-nav-card.py --pwd <PWD>
```
Expected : deploy = re-upsert sans erreur (même contenu) ; patch nav = `Already patched (idempotent skip)`.

---

### Task 5 : Validation prod + rapport

**Files:** aucun.

- [ ] **Step 1 : Vérifications REST**

Via GET `/api/dashboard/0964da30-3e56-11f1-bbfe-e1395562cba0` (token comme dans les scripts) :
1. `configuration.states.ecs` existe, `name == 'Eau chaude sanitaire'`, 1 seul widget `a1b2c3d4-0720-...` en layout 24×24, gridSettings.autoFillHeight true (hérité de depart_chauffage) ;
2. `configuration.widgets['a1b2c3d4-0720-...'].config.settings.markdownTextFunction` contient `__ECS_UNIFIED_V1__`, `__tbEcsUnified`, `pumpsInfo` ;
3. le markdown de `a1b2c3d4-d600-...` contient `__ECSNAV_V1__`.

- [ ] **Step 2 : Validation visuelle (user, parc actuel = type 0/1)**

Demander au user de vérifier dans le navigateur :
1. état `default` d'une installation : la carte « Module ECS » n'est **pas** cliquable (type 0/1 → pas de hover ni « Voir détails ») ;
2. accès direct à l'état ecs par URL (`?state=` base64 de `[{"id":"ecs","params":{...entityId...}}]`) : message « Pas de module ECS sur cette installation », pas de courbe ;
3. la page chauffage `depart_chauffage` fonctionne toujours (non-régression : namespace `__tbEcsUnified` distinct, listener retroview séparé).

Pour prévisualiser le rendu complet (courbe + 4 tableaux pompes) sans installation type 2/3 : dans la console du navigateur sur la page ecs, forcer `window.__tbEcsUnified` → non trivial ; plus simple : noter que la validation complète attend la première installation type 2/3 en ligne (consigné dans la spec).

- [ ] **Step 3 : Rapport final**

Résumer : versions dashboard avant/après, vérifications REST, points en attente (validation visuelle type 2/3, bascule `pumpPresent()` vers les attributs automate à venir — cf. mémoire `ecs-pump-presence-keys`). Rollback = re-POST du backup `backup-mes-installations.before_ecs_state.<ts>.json`.
