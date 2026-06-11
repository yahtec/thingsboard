// __PAC_UNIFIED_V1__
// Widget markdown_card unifie : fusionne les 10 widgets de l'etat donnees_HP1 en un seul.
// Structure : [A] helpers PACV2  [B] ctx/resolve/time  [C] CHARTS  [D] HTML  [E] setTimeout
//             [F] loop  [F2] fetchEvt  [G] renderChart  [H] buildPacInfo
// Tout est en `function` declarations (hoistees) ; on calcule ctxRef/P/pre/CHARTS/html en
// `var`, on planifie le setTimeout, puis on `return html;` en DERNIERE instruction.

// =====================================================================================
// [A] helpers verbatim from pac_chart_temperatures.fn.js
// =====================================================================================
function PACV2_FLATTEN(p) {
    var out = {};
    if (!p || typeof p !== 'object') return out;
    for (var __k in p) {
        var __v = p[__k];
        if (__v === null || __v === undefined) continue;
        if (typeof __v !== 'object') out[__k] = __v;
    }
    if (Array.isArray(p.HPs)) {
        for (var __i = 0; __i < p.HPs.length; __i++) {
            var __hp = p.HPs[__i] || {}, __pfx = 'HP' + (__i + 1);
            if (__hp.HP)     for (var __k2 in __hp.HP)     out[__pfx + '_' + __k2] = __hp.HP[__k2];
            if (__hp.invert) for (var __k2 in __hp.invert) out[__pfx + '_invert_' + __k2] = __hp.invert[__k2];
            if (__hp.boil)   for (var __k2 in __hp.boil)   out[__pfx + '_boil_' + __k2] = __hp.boil[__k2];
            if (__hp.pump)   for (var __k2 in __hp.pump)   out[__pfx + '_pump_' + __k2] = __hp.pump[__k2];
            ['comm', 'relStm', 'relEsp', 'relScr'].forEach(function(__k3) {
                if (__hp[__k3] !== undefined) out[__pfx + '_' + __k3] = __hp[__k3];
            });
        }
    }
    if (p.dhw) for (var __k in p.dhw) {
        var __v = p.dhw[__k];
        if (__v === null || __v === undefined) continue;
        var __m = __k.match(/^pump([1-4])$/);
        if (__m && typeof __v === 'object') {
            for (var __k2 in __v) out['dhw_pump' + __m[1] + '_' + __k2] = __v[__k2];
        } else if (typeof __v !== 'object') {
            out['dhw_' + __k] = __v;
        }
    }
    if (p.heat) for (var __k in p.heat) {
        var __v = p.heat[__k];
        if (__v === null || __v === undefined) continue;
        if (__k === 'calo' && typeof __v === 'object') {
            for (var __k2 in __v) out['heat_calo_' + __k2] = __v[__k2];
        } else if (typeof __v !== 'object') {
            out['heat_' + __k] = __v;
        }
    }
    if (p.caloM) for (var __k in p.caloM) {
        var __v = p.caloM[__k];
        if (__v !== null && __v !== undefined && typeof __v !== 'object') out['caloM_' + __k] = __v;
    }
    ['pump1M', 'pump2M'].forEach(function(__name) {
        if (p[__name]) for (var __k in p[__name]) {
            var __v = p[__name][__k];
            if (__v !== null && __v !== undefined && typeof __v !== 'object') out[__name + '_' + __k] = __v;
        }
    });
    return out;
}

function PACV2_TO_SERIES(d, expectedKeys) {
    var pacPoints = d.pac_v2 || [];
    var newSeries = {};
    expectedKeys.forEach(function(k) { newSeries[k] = []; });
    pacPoints.forEach(function(p) {
        var ts = parseInt(p.ts, 10);
        var raw = p.value;
        try {
            var pv = (typeof raw === 'string') ? JSON.parse(raw) : raw;
            var flat = PACV2_FLATTEN(pv);
            expectedKeys.forEach(function(k) {
                var v = flat[k];
                if (v !== null && v !== undefined) {
                    newSeries[k].push({ ts: ts, value: v });
                }
            });
        } catch (e) {}
    });
    return newSeries;
}

// =====================================================================================
// [B] ctxRef + resolve* + time helpers  (CRITICAL: P/pre computed here, before [C])
// =====================================================================================
var ctxRef = (typeof ctx!=='undefined'&&ctx)?ctx:(typeof self!=='undefined'?self.ctx:null);
function resolveHpIndex(c){ try{ var sp=c&&c.stateController?c.stateController.getStateParams():null; if(sp&&sp.hpIndex) return Number(sp.hpIndex);}catch(_){ } return 1; }
function resolveDevice(){ try{ var d=ctxRef&&ctxRef.datasources&&ctxRef.datasources[0]; if(d&&d.entityId) return d.entityId; if(d&&d.entity&&d.entity.id) return d.entity.id.id; }catch(e){} return null; }
function getToken(){ return localStorage.getItem('jwt_token'); }

function getTimeWindow() {
    var __h = 3600000;
    var __btn = parseInt(sessionStorage.getItem('tduo.timeline.buttonH') || '24', 10);
    var __zoom = parseInt(sessionStorage.getItem('tduo.timeline.zoomPct') || '100', 10);
    if (isNaN(__btn) || __btn <= 0)  __btn = 24;
    if (isNaN(__zoom) || __zoom < 5) __zoom = 5;
    if (__zoom > 100) __zoom = 100;
    var __spanMs = Math.round(__btn * __zoom / 100 * __h);
    if (__spanMs < 60000) __spanMs = 60000;
    var __rv = sessionStorage.getItem('tduo.retroview.endTs');
    var __endRaw;
    if (__rv) {
        __endRaw = parseInt(__rv, 10);
        if (isNaN(__endRaw) || __endRaw <= 0) __endRaw = Date.now();
    } else {
        __endRaw = Date.now();
    }
    var __end = Math.ceil(__endRaw / 60000) * 60000;
    return { startTs: __end - __spanMs, endTs: __end };
}

function getAggInterval(win) {
    var span = win.endTs - win.startTs;
    var iv = Math.max(1000, Math.round(span / 300));
    var steps = [1000, 5000, 10000, 30000, 60000, 300000, 600000, 900000, 1800000, 3600000, 7200000, 14400000, 86400000];
    for (var i = 0; i < steps.length; i++) {
        if (iv <= steps[i]) return steps[i];
    }
    return 86400000;
}

// =====================================================================================
// [C] CHARTS specs (P/pre assigned BEFORE the array literal)
// =====================================================================================
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
window.__CHARTS_BOIL = CHARTS_BOIL;

// =====================================================================================
// [D] HTML skeleton builder
// =====================================================================================
function chartCard(c){ return '<div class="u-card u-chart" id="u-err-'+c.id+'-wrap"><div class="u-chart-title">'+c.title+'</div>'+
  '<div class="u-chart-body"><svg id="'+c.svg+'" preserveAspectRatio="xMidYMid meet"></svg>'+
  '<div id="'+c.svg+'-tip" style="display:none;position:absolute;background:rgba(0,0,0,0.75);color:#fff;padding:8px 12px;border-radius:6px;font-size:12px;pointer-events:none;z-index:10"></div></div>'+
  '<div id="'+c.svg+'-leg" class="u-chart-legend"></div><div id="u-err-'+c.id+'"></div></div>'; }
var html = '<div class="u-root">'+
  '<div id="u-banner" class="u-err" style="display:none"></div>'+
  '<div class="u-scroll">'+
    '<div class="u-tl" id="u-timeline"></div>'+
    '<div class="u-section"><div id="u-pac-info"></div><div id="u-err-pacinfo"></div>'+
      '<div class="u-grid">'+CHARTS.map(chartCard).join('')+'</div></div>'+
    '<div class="u-section" id="u-boiler"><div id="u-boil-info"></div><div id="u-err-boilinfo"></div>'+
      '<div class="u-grid">'+CHARTS_BOIL.map(chartCard).join('')+'</div></div>'+
    '<div class="u-section" id="u-usage"></div>'+
  '</div></div>';

// =====================================================================================
// [E] setTimeout + responsive
// =====================================================================================
function wireResponsiveGrid(){
  var grids = document.querySelectorAll('.u-grid');
  function apply(){ var w = (document.querySelector('.u-scroll')||{}).clientWidth || 1000;
    var cols = w < 600 ? '1fr' : '1fr 1fr';
    grids.forEach(function(g){ g.style.gridTemplateColumns = cols; }); if(window.__tbPacUnified.onResize) window.__tbPacUnified.onResize(); }
  apply();
  var ro = (typeof ResizeObserver !== 'undefined') ? new ResizeObserver(apply) : null;
  var sc = document.querySelector('.u-scroll'); if(ro && sc) ro.observe(sc);
  window.__tbPacUnified.ro = ro;
}
setTimeout(function(){
  var prev = window.__tbPacUnified || {};
  if (prev.timer) clearInterval(prev.timer);
  if (prev.ro) { try{ prev.ro.disconnect(); }catch(e){} }
  if (prev.listeners) Object.keys(prev.listeners).forEach(function(k){ try { document.removeEventListener('mousemove', prev.listeners[k]); } catch(e){} });
  window.__tbPacUnified = { vis:{}, listeners:{} };
  try { wireResponsiveGrid(); } catch(e){ console.warn('[unified] responsive', e); }
  startSharedLoop();
}, 60);

// =====================================================================================
// [F] startSharedLoop / renderAll / safe / showBanner
// =====================================================================================
function startSharedLoop() {
  var DEVICE_ID = resolveDevice();
  if (!DEVICE_ID) { console.warn('[unified] no device'); return; }
  window.__tbPacUnified.refetch = fetchShared;
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
  if (window.__renderBoiler) window.__renderBoiler(seriesData, latestFlat, win, evt);
}
function safe(tag, fn){ try { fn(); } catch(e){ var el=document.getElementById('u-err-'+tag); if(el) el.innerHTML='<div class="u-err">Section '+tag+' indisponible</div>'; console.warn('[unified]', tag, e); } }
function showBanner(msg){ var el=document.getElementById('u-banner'); if(el){ el.textContent=msg; el.style.display='block'; } }

// =====================================================================================
// [F2] fetchEvt  (ported from __EVT_FETCH ; throttle via EVT.last)
// =====================================================================================
function fetchEvt(deviceId, win, EVT, cb) {
    if (!deviceId) return;
    var now = Date.now();
    if (now - EVT.last < 30000) return;
    EVT.last = now;
    var LOOKBACK_DAYS = 90;
    var endTs = now;
    var startTs = now - LOOKBACK_DAYS * 86400000;
    var keys = 'evt_id,evt_status,evt_fault,evt_device';
    var url = '/api/plugins/telemetry/DEVICE/' + deviceId +
        '/values/timeseries?keys=' + keys +
        '&startTs=' + startTs + '&endTs=' + endTs + '&agg=NONE&limit=500&orderBy=DESC';
    fetch(url, { headers: { 'X-Authorization': 'Bearer ' + getToken() } })
        .then(function(r) { return r.json(); })
        .then(function(d) {
            var FAULT_CODES = {15:1,29:1,38:1,39:1,40:1,88:1};
            var PAC_DEVICES = {50:1,51:1,52:1,53:1,54:1,55:1};
            var byTs = {};
            ['evt_id','evt_status','evt_fault','evt_device'].forEach(function(k) {
                (d[k] || []).forEach(function(dp) {
                    var ts = dp.ts;
                    if (!byTs[ts]) byTs[ts] = {ts: ts};
                    byTs[ts][k] = Number(dp.value);
                });
            });
            var pts = Object.keys(byTs).map(function(k) { return byTs[k]; })
                .filter(function(p) { return p.evt_status !== undefined && p.evt_fault !== undefined && p.evt_device !== undefined; })
                .sort(function(a, b) { return a.ts - b.ts; });
            var openMap = {};
            var intervals = [];
            pts.forEach(function(p) {
                if (!PAC_DEVICES[p.evt_device] || !FAULT_CODES[p.evt_fault]) return;
                var realTs = p.evt_id > 0 ? p.evt_id * 1000 : p.ts;
                var key = p.evt_device + ':' + p.evt_fault;
                if (p.evt_status === 1) {
                    if (openMap[key] === undefined) openMap[key] = realTs;
                } else if (p.evt_status === 0) {
                    if (openMap[key] !== undefined) {
                        intervals.push({ start: openMap[key], end: realTs });
                        delete openMap[key];
                    }
                }
            });
            Object.keys(openMap).forEach(function(key) {
                intervals.push({ start: openMap[key], end: Date.now() });
            });
            EVT.intervals = intervals;
            console.log('[unified evt] reconstructed ' + intervals.length + ' interval(s) from ' + pts.length + ' point(s)');
            if (typeof cb === 'function') cb();
        })
        .catch(function(e) { console.warn('[unified evt] fetch failed', e); });
}
function __EVT_RECTS(intervals, padL, padT, iw, ih, xOf, tw) {
    if (!intervals || !intervals.length) return '';
    var s = '';
    intervals.forEach(function(iv) {
        var s0 = Math.max(iv.start, tw.startTs);
        var e0 = Math.min(iv.end, tw.endTs);
        if (e0 <= s0) return;
        var x0 = xOf(s0), x1 = xOf(e0);
        var bw = Math.max(1, x1 - x0);
        s += '<rect x="' + x0.toFixed(1) + '" y="' + padT + '" width="' + bw.toFixed(1) + '" height="' + ih + '" fill="#888" fill-opacity="0.18" pointer-events="none"/>';
    });
    return s;
}

// =====================================================================================
// [G] renderChart(cfg, seriesData, win, evtIntervals)  (ported engine)
// =====================================================================================
function isBadChart(v) {
    // Sentinelles firmware: -99.9 (sonde deconnectee) ET -47.8 (code de defaut).
    // Aucune sonde HVAC reelle ne descend sous -45 degC.
    return v == null || isNaN(v) || v <= -45;
}
function smoothPath(pts) {
    var n = pts.length;
    if (n === 0) return '';
    if (n === 1) return 'M' + pts[0].x.toFixed(1) + ',' + pts[0].y.toFixed(1);
    if (n === 2) return 'M' + pts[0].x.toFixed(1) + ',' + pts[0].y.toFixed(1)
                      + 'L' + pts[1].x.toFixed(1) + ',' + pts[1].y.toFixed(1);
    var m = new Array(n - 1);
    for (var i = 0; i < n - 1; i++) {
        var dx = pts[i+1].x - pts[i].x;
        m[i] = dx === 0 ? 0 : (pts[i+1].y - pts[i].y) / dx;
    }
    var t = new Array(n);
    t[0] = m[0];
    t[n-1] = m[n-2];
    for (var i = 1; i < n - 1; i++) {
        if (m[i-1] * m[i] <= 0) {
            t[i] = 0;
        } else {
            t[i] = (m[i-1] + m[i]) / 2;
            var a = m[i-1] === 0 ? 0 : t[i] / m[i-1];
            var b = m[i]   === 0 ? 0 : t[i] / m[i];
            if (a > 3) t[i] = 3 * m[i-1];
            if (b > 3) t[i] = 3 * m[i];
        }
    }
    var path = 'M' + pts[0].x.toFixed(1) + ',' + pts[0].y.toFixed(1);
    for (var i = 0; i < n - 1; i++) {
        var dx = pts[i+1].x - pts[i].x;
        var c1x = pts[i].x   + dx / 3;
        var c1y = pts[i].y   + t[i]   * dx / 3;
        var c2x = pts[i+1].x - dx / 3;
        var c2y = pts[i+1].y - t[i+1] * dx / 3;
        path += 'C' + c1x.toFixed(1) + ',' + c1y.toFixed(1)
              + ' ' + c2x.toFixed(1) + ',' + c2y.toFixed(1)
              + ' ' + pts[i+1].x.toFixed(1) + ',' + pts[i+1].y.toFixed(1);
    }
    return path;
}
function renderChart(cfg, seriesData, win, evtIntervals) {
    var svg = document.getElementById(cfg.svg);
    if (!svg) return;
    var SERIES = cfg.series;
    var AXIS = JSON.parse(JSON.stringify(cfg.axis));
    // formatters perdus par le deep-copy JSON : on les reaffecte
    AXIS.left.fmt = function(v){ return v.toFixed(0); }; AXIS.left.color = '#555';
    AXIS.freq.fmt = function(v){ return v.toFixed(0); }; AXIS.freq.color = '#66bb6a';
    AXIS.pwr.fmt  = function(v){ return (v/1000).toFixed(0); }; AXIS.pwr.color = '#ab47bc';
    AXIS.dpf.fmt  = function(v){ return v.toFixed(0); }; AXIS.dpf.color = '#5c6bc0';
    var showAxes = false;

    // visibility scope par chart id
    window.__tbPacUnified.vis[cfg.id] = window.__tbPacUnified.vis[cfg.id] || {};
    var visibility = window.__tbPacUnified.vis[cfg.id];
    SERIES.forEach(function(s) { if (!(s.key in visibility)) visibility[s.key] = true; });

    var tw = win;

    function drawChart() {
        var svg = document.getElementById(cfg.svg);
        if (!svg) return;
        // Echelle pwr dynamique
        var _pwrKey = pre+'invert_pwr';
        var _pwrMax = 0;
        (seriesData[_pwrKey] || []).forEach(function(p) {
            var v = parseFloat(p.value);
            if (!isNaN(v) && v > _pwrMax) _pwrMax = v;
        });
        var _pwrFloor = 30000;
        if (_pwrMax > _pwrFloor) {
            AXIS.pwr.max = Math.ceil(_pwrMax / 5000) * 5000;
        } else {
            AXIS.pwr.max = _pwrFloor;
        }
        var container = svg.parentElement;
        var w = Math.max(320, Math.round(container.clientWidth || 1000));
        var h = Math.max(180, Math.round(container.clientHeight || 300));
        svg.setAttribute('viewBox', '0 0 '+w+' '+h);
        var hasFreq = SERIES.some(function(s){ return s.axis==='freq' && visibility[s.key]; });
        var hasPwr  = SERIES.some(function(s){ return s.axis==='pwr'  && visibility[s.key]; });
        var hasDpf  = SERIES.some(function(s){ return s.axis==='dpf'  && visibility[s.key]; });
        var narrow = w < 600;
        var showPwrLabels = hasPwr;
        var padL = showAxes ? 40 : 12;
        var padR = 12;
        var kwOffset = narrow ? 26 : 33;
        var dpfOffset = narrow ? 52 : 66;
        if (showAxes && hasFreq)      padR += narrow ? 24 : 28;
        if (showAxes && showPwrLabels) padR += narrow ? 26 : 30;
        if (showAxes && hasDpf)        padR += narrow ? 26 : 30;
        var padT = 20, padB = narrow ? 46 : 32;
        var iw = w - padL - padR, ih = h - padT - padB;
        function xOf(ts) { return padL + ((ts - tw.startTs) / (tw.endTs - tw.startTs)) * iw; }
        function yOf(axisId, v) {
            var a = AXIS[axisId];
            return padT + ih - ((v - a.min) / (a.max - a.min)) * ih;
        }
        var sc = '';
        var yTicks = ih >= 260 ? 6 : (ih >= 160 ? 4 : 3);
        for (var i = 0; i <= yTicks; i++) {
            var t = i / yTicks;
            var y = padT + t * ih;
            sc += '<line x1="'+padL+'" y1="'+y+'" x2="'+(padL+iw)+'" y2="'+y+'" stroke="#eee" stroke-width="1"/>';
            var vL = AXIS.left.max - t * (AXIS.left.max - AXIS.left.min);
            if (showAxes) sc += '<text x="'+(padL-6)+'" y="'+(y+4)+'" text-anchor="end" font-size="10" fill="'+AXIS.left.color+'">'+AXIS.left.fmt(vL)+'</text>';
            if (hasFreq) {
                var vF = AXIS.freq.max - t * (AXIS.freq.max - AXIS.freq.min);
                if (showAxes) sc += '<text x="'+(padL+iw+5)+'" y="'+(y+4)+'" text-anchor="start" font-size="10" fill="'+AXIS.freq.color+'">'+AXIS.freq.fmt(vF)+'</text>';
            }
            if (showPwrLabels) {
                var vP = AXIS.pwr.max - t * (AXIS.pwr.max - AXIS.pwr.min);
                if (showAxes) sc += '<text x="'+(padL+iw+kwOffset)+'" y="'+(y+4)+'" text-anchor="start" font-size="10" fill="'+AXIS.pwr.color+'">'+AXIS.pwr.fmt(vP)+'</text>';
            }
            if (hasDpf) {
                var vD = AXIS.dpf.max - t * (AXIS.dpf.max - AXIS.dpf.min);
                if (showAxes) sc += '<text x="'+(padL+iw+dpfOffset)+'" y="'+(y+4)+'" text-anchor="start" font-size="10" fill="'+AXIS.dpf.color+'">'+AXIS.dpf.fmt(vD)+'</text>';
            }
        }
        if (showAxes && hasFreq) sc += '<text x="'+(padL+iw+5)+'" y="'+(padT-8)+'" text-anchor="start" font-size="9" fill="'+AXIS.freq.color+'">Hz</text>';
        if (showAxes && showPwrLabels) sc += '<text x="'+(padL+iw+kwOffset)+'" y="'+(padT-8)+'" text-anchor="start" font-size="9" fill="'+AXIS.pwr.color+'">kW</text>';
        if (showAxes && hasDpf) sc += '<text x="'+(padL+iw+dpfOffset)+'" y="'+(padT-8)+'" text-anchor="start" font-size="9" fill="'+AXIS.dpf.color+'">pas</text>';
        var span = tw.endTs - tw.startTs;
        var targetTicks = Math.max(4, Math.min(10, Math.floor(iw / 70)));
        var roughStep = span / targetTicks;
        var steps = [300000, 600000, 900000, 1800000, 3600000, 7200000, 10800000, 14400000, 21600000, 43200000, 86400000, 2*86400000, 7*86400000, 14*86400000, 30*86400000];
        var tickStep = steps[steps.length-1];
        for (var si = 0; si < steps.length; si++) { if (steps[si] >= roughStep) { tickStep = steps[si]; break; } }
        var tickFmt = span <= 48*3600000 ? 'hm' : (span <= 14*86400000 ? 'dhm' : (span <= 180*86400000 ? 'md' : 'my'));
        var firstTick = Math.ceil(tw.startTs / tickStep) * tickStep;
        var rotate = narrow ? -40 : 0;
        for (var t2 = firstTick; t2 <= tw.endTs; t2 += tickStep) {
            var x = xOf(t2); if (x < padL || x > padL+iw) continue;
            sc += '<line x1="'+x+'" y1="'+padT+'" x2="'+x+'" y2="'+(padT+ih)+'" stroke="#f0f0f0" stroke-width="1"/>';
            var dd = new Date(t2), p2 = function(n){return n<10?'0'+n:n;};
            var lbl;
            if (tickFmt === 'hm')       lbl = p2(dd.getHours())+':'+p2(dd.getMinutes());
            else if (tickFmt === 'dhm') lbl = p2(dd.getDate())+'/'+p2(dd.getMonth()+1)+' '+p2(dd.getHours())+'h';
            else if (tickFmt === 'md')  lbl = p2(dd.getDate())+'/'+p2(dd.getMonth()+1);
            else                        lbl = p2(dd.getMonth()+1)+'/'+dd.getFullYear();
            var labelY = padT + ih + (rotate ? 14 : 18);
            var anchor = rotate ? 'end' : 'middle';
            var rot = rotate ? ' transform="rotate('+rotate+' '+x+' '+labelY+')"' : '';
            sc += '<text x="'+x+'" y="'+labelY+'" text-anchor="'+anchor+'" font-size="10" fill="#666"'+rot+'>'+lbl+'</text>';
        }
        sc += '<line x1="'+padL+'" y1="'+padT+'" x2="'+padL+'" y2="'+(padT+ih)+'" stroke="#bbb" stroke-width="1"/>';
        sc += '<line x1="'+(padL+iw)+'" y1="'+padT+'" x2="'+(padL+iw)+'" y2="'+(padT+ih)+'" stroke="#bbb" stroke-width="1"/>';
        sc += '<line x1="'+padL+'" y1="'+(padT+ih)+'" x2="'+(padL+iw)+'" y2="'+(padT+ih)+'" stroke="#bbb" stroke-width="1"/>';
        sc += __EVT_RECTS(evtIntervals, padL, padT, iw, ih, xOf, tw);
        SERIES.forEach(function(s) {
            if (!visibility[s.key]) return;
            var arr = (seriesData[s.key] || []).slice().reverse();
            if (arr.length < 1) return;
            if (s.axis === 'left') {
                var anyReal = false;
                for (var _i = 0; _i < arr.length; _i++) {
                    var _v = parseFloat(arr[_i].value);
                    if (!isBadChart(_v) && _v !== 0) { anyReal = true; break; }
                }
                if (!anyReal) return;
            }
            var segments = [], current = [];
            for (var i = 0; i < arr.length; i++) {
                var p = arr[i], v = parseFloat(p.value);
                if (isBadChart(v)) { if (current.length) { segments.push(current); current = []; } continue; }
                current.push({ x: xOf(p.ts), y: yOf(s.axis, v) });
            }
            if (current.length) segments.push(current);
            var d = '';
            for (var si2 = 0; si2 < segments.length; si2++) { d += smoothPath(segments[si2]); }
            if (d) sc += '<path d="'+d+'" fill="none" stroke="'+s.color+'" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
        });
        svg.innerHTML = sc;
    }

    function drawLegend() {
        var legend = document.getElementById(cfg.svg+'-leg'); if (!legend) return;
        legend.innerHTML = '';
        legend.style.cssText = 'display:flex;flex-wrap:wrap;gap:10px;padding-top:6px;border-top:1px solid #eee;';
        SERIES.forEach(function(s) {
            var item = document.createElement('div');
            var active = visibility[s.key];
            item.style.cssText = 'display:inline-flex;align-items:center;gap:6px;cursor:pointer;padding:4px 10px;border-radius:4px;font-size:12px;user-select:none;background:#f5f5f5;'+(active?'':'opacity:0.4;text-decoration:line-through;');
            item.innerHTML = '<span style="display:inline-block;width:12px;height:12px;border-radius:2px;background:'+s.color+'"></span>'+s.label;
            item.addEventListener('click', function() {
                visibility[s.key] = !visibility[s.key];
                drawChart(); drawLegend();
            });
            legend.appendChild(item);
        });
    }

    function onMouseMove(evt) {
        var svg = document.getElementById(cfg.svg);
        var tip = document.getElementById(cfg.svg+'-tip');
        if (!svg || !tip) return;
        var rect = svg.getBoundingClientRect();
        if (evt.clientX < rect.left || evt.clientX > rect.right || evt.clientY < rect.top || evt.clientY > rect.bottom) { tip.style.display='none'; return; }
        var hasFreq = SERIES.some(function(s){ return s.axis==='freq' && visibility[s.key]; });
        var hasPwr  = SERIES.some(function(s){ return s.axis==='pwr'  && visibility[s.key]; });
        var hasDpf  = SERIES.some(function(s){ return s.axis==='dpf'  && visibility[s.key]; });
        var narrow = rect.width < 600;
        var showPwrLabels = hasPwr;
        var padL = showAxes ? 40 : 12, padR = 12;
        if (showAxes && hasFreq)      padR += narrow ? 24 : 28;
        if (showAxes && showPwrLabels) padR += narrow ? 26 : 30;
        if (showAxes && hasDpf)        padR += narrow ? 26 : 30;
        if (evt.clientX-rect.left < padL || evt.clientX-rect.left > rect.width-padR) { tip.style.display='none'; return; }
        var innerW = rect.width - padL - padR;
        var ts = tw.startTs + ((evt.clientX-rect.left-padL)/innerW)*(tw.endTs-tw.startTs);
        var lines = [];
        SERIES.forEach(function(s) {
            if (!visibility[s.key]) return;
            var arr = (seriesData[s.key] || []).filter(function(p) { return !isBadChart(parseFloat(p.value)); });
            var valStr;
            if (!arr.length) {
                valStr = '--';
            } else {
                var best = arr[0], minD = Math.abs(arr[0].ts-ts);
                for (var i=1;i<arr.length;i++) { var d=Math.abs(arr[i].ts-ts); if (d<minD){minD=d;best=arr[i];} }
                valStr = parseFloat(best.value).toFixed(1)+s.unit;
            }
            lines.push('<span style="color:'+s.color+'">&#9632;</span> '+s.label+' : '+valStr);
        });
        if (!lines.length) { tip.style.display='none'; return; }
        var dd=new Date(ts), pad=function(n){return n<10?'0'+n:n;};
        tip.innerHTML = '<div style="font-weight:bold;margin-bottom:4px">'+pad(dd.getDate())+'/'+pad(dd.getMonth()+1)+' '+pad(dd.getHours())+':'+pad(dd.getMinutes())+'</div>'+lines.join('<br>');
        tip.style.display='block';
        tip.style.left='0px'; tip.style.top='0px';
        var tw_w = tip.offsetWidth, tw_h = tip.offsetHeight;
        var px = evt.clientX - rect.left + 10;
        var py = evt.clientY - rect.top  + 10;
        if (px + tw_w > rect.width - 4) px = (evt.clientX - rect.left) - tw_w - 10;
        if (py + tw_h > rect.height - 4) py = (evt.clientY - rect.top) - tw_h - 10;
        if (px < 0) px = 0;
        if (py < 0) py = 0;
        tip.style.left = px + 'px';
        tip.style.top  = py + 'px';
    }

    // Tooltip listener lifecycle: une seule ecoute par cfg.id, remplacee a chaque re-render
    // pour ne pas empiler de listeners au fil des refresh 30s.
    var L = window.__tbPacUnified.listeners = window.__tbPacUnified.listeners || {};
    if (L[cfg.id]) document.removeEventListener('mousemove', L[cfg.id]);
    L[cfg.id] = onMouseMove;
    document.addEventListener('mousemove', onMouseMove);

    drawChart();
    drawLegend();
}

// =====================================================================================
// [H] buildPacInfo(e)  (ported from pac_info.fn.js) + shared isBad/fv/buildValueRow/tH
// =====================================================================================
function isBad(val) {
    if (val === null || val === undefined || val === '') return true;
    var n = parseFloat(val);
    return isNaN(n) || n <= -45;
}
function fv(val, unit, decimals) {
    if (isBad(val)) return '--';
    return parseFloat(val).toFixed(decimals !== undefined ? decimals : 1) + (unit || '');
}
function buildValueRow(label, value, unit, decimals) {
    return '<div class="val-row"><span class="val-label">'+label+'</span><span class="val-value">'+fv(value,unit,decimals)+'</span></div>';
}
function tH(v) {
    if (v === null || v === undefined || v === '') return v;
    var n = Number(v);
    if (!isFinite(n)) return v;
    return n / 3600; // firmware emet des secondes -> heures
}
function infoFrame(title, innerHtml){
  return '<div style="background:#f5f5f5;border-radius:8px;padding:12px;box-shadow:0 2px 8px rgba(0,0,0,0.1);box-sizing:border-box">'+
    '<div style="font-size:16px;font-weight:700;color:#333;text-transform:uppercase;letter-spacing:1px;padding-bottom:8px;border-bottom:1px solid #e0e0e0;margin-bottom:10px">'+title+'</div>'+
    innerHtml+'</div>';
}
function infoTable(rows){
  var body = rows.map(function(r,i){
    var bb = i < rows.length-1 ? 'border-bottom:1px solid #eee;' : '';
    return '<tr>'+
      '<td style="font-size:11px;color:#666;text-transform:uppercase;letter-spacing:0.3px;padding:4px 8px 4px 0;'+bb+'">'+r[0]+'</td>'+
      '<td style="font-size:14px;font-weight:bold;color:#333;text-align:right;white-space:nowrap;padding:4px 0;'+bb+'">'+r[1]+'</td>'+
      '</tr>';
  }).join('');
  return '<table style="width:100%;border-collapse:collapse;background:#fff;border-radius:6px;padding:6px 12px;box-shadow:0 1px 4px rgba(0,0,0,0.08);box-sizing:border-box"><tbody>'+body+'</tbody></table>';
}
function infoSub(title){ return '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:#888;margin:0 0 4px">'+title+'</div>'; }
function buildPacInfo(e){
  e = e || {};
  return infoFrame('PAC Hybride n'+P, infoTable([
    ['Fréquence compresseur', fv(e[pre+'invert_freq'],' Hz',1)],
    ['Puissance compresseur', fv(e[pre+'invert_pwr'],' W',0)],
    ['Vitesse ventilateur', fv(e[pre+'rpm'],' rpm',0)],
    ['Position détendeur', fv(e[pre+'dpf'],'',0)],
    ['T° surchauffe', fv(e[pre+'tOH'],'°C',1)],
    ['Temps de fonctionnement', fv(tH(e[pre+'time']),' h',0)]
  ]));
}
function buildBoilerInfo(e){
  e = e || {};
  var chaud = infoSub('Chaudière') + infoTable([
    ['T° entrée', fv(e[pre+'tOut'],'°C',1)],
    ['T° sortie', fv(e[pre+'boil_tOut'],'°C',1)],
    ['T° fumée', fv(e[pre+'boil_tSmoke'],'°C',1)],
    ['Débit eau', fv(e[pre+'boil_qe'],' L/h',0)],
    ['Vitesse brûleur', fv(e[pre+'boil_rpm'],' rpm',0)],
    ['Temps de fonctionnement', fv(tH(e[pre+'boil_time']),' h',0)]
  ]);
  var pompe = infoSub('Pompe') + infoTable([
    ['Vitesse', fv(e[pre+'pump_rpm'],' rpm',0)],
    ['DeltaP', fv(e[pre+'pump_dP'],' mCE',2)],
    ['Puissance', fv(e[pre+'pump_pwr'],' W',0)],
    ['Débit', fv(e[pre+'pump_qe'],' L/h',0)],
    ['Durée ON', fv(tH(e[pre+'pump_time']),' h',0)]
  ]);
  return infoFrame('Données Chaudière '+P,
    '<div style="display:flex;flex-wrap:wrap;gap:10px">'+
      '<div style="flex:1 1 220px;min-width:200px">'+chaud+'</div>'+
      '<div style="flex:1 1 220px;min-width:200px">'+pompe+'</div>'+
    '</div>');
}

window.__renderBoiler = function(seriesData, latestFlat, win, evt){
  safe('boilinfo', function(){ var el=document.getElementById('u-boil-info'); if(el) el.innerHTML=buildBoilerInfo(latestFlat); });
  CHARTS_BOIL.forEach(function(c){ safe(c.id, function(){ renderChart(c, seriesData, win, evt); }); });
};

return html;
