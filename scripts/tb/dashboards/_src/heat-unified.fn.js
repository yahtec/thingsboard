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
var HEAT_CHART = {
  id:'heat', title:'Chauffage', svg:'u-svg-heat',
  series:[{key:'heat_setpoint',label:'Consigne départ',color:'#7cb342',axis:'left',unit:'°C'},
          {key:'heat_tOut',    label:'T° départ chauffage',color:'#ef5350',axis:'left',unit:'°C'},
          {key:'heat_tIn',     label:'T° retour chauffage',color:'#42a5f5',axis:'left',unit:'°C'},
          {key:'tExt',         label:'T° extérieure',color:'#90a4ae',axis:'left',unit:'°C'}],
  axis:{left:{min:-20,max:90},freq:{min:0,max:120},pwr:{min:0,max:30000},dpf:{min:0,max:2200}}
};

// =====================================================================================
// [D] HTML skeleton builder
// =====================================================================================
function chartCard(c){ return '<div class="u-card u-chart" id="u-err-'+c.id+'-wrap"><div class="u-chart-title">'+c.title+'</div>'+
  '<div class="u-chart-body"><svg id="'+c.svg+'" preserveAspectRatio="xMidYMid meet"></svg>'+
  '<div id="'+c.svg+'-tip" style="display:none;position:absolute;background:rgba(0,0,0,0.75);color:#fff;padding:8px 12px;border-radius:6px;font-size:12px;pointer-events:none;z-index:10"></div></div>'+
  '<div id="'+c.svg+'-leg" class="u-chart-legend"></div><div id="u-err-'+c.id+'"></div></div>'; }

// --- Timeline (window bar) + retroview control HTML, injected into #u-timeline ---
// Porte de timeline.fn.js (boutons fenetre + zoom) + pac_info.fn.js (bouton retroview).
var TL_MIN_ZOOM = 5;
function buildTimelineBar(){
  var btns = ['4','8','12','24'].map(function(h){
    return '<button type="button" data-h="'+h+'" class="u-tl-btn" style="border:1px solid #ddd;background:#f5f5f5;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600">'+h+' h</button>';
  }).join('');
  return ''+
  '<div style="background:#fff;border:1px solid #e0e0e0;border-radius:8px;padding:8px 14px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;box-sizing:border-box;align-content:center">'+
    '<div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#333;letter-spacing:0.5px">Fenetre</div>'+
    '<div class="u-tl-btns" style="display:flex;gap:4px">'+btns+'</div>'+
    '<div style="flex:1;min-width:220px;display:flex;gap:8px;align-items:center">'+
      '<span style="font-size:11px;color:#888;min-width:36px">100%</span>'+
      '<input type="range" min="'+TL_MIN_ZOOM+'" max="100" value="100" step="1" class="u-tl-slider" style="flex:1;accent-color:#5c6bc0;transform:scaleX(-1)" />'+
      '<span style="font-size:11px;color:#888;min-width:24px;text-align:right">'+TL_MIN_ZOOM+'%</span>'+
    '</div>'+
    '<div class="u-tl-label" style="font-size:12px;color:#333;min-width:170px;font-variant-numeric:tabular-nums"></div>'+
    /* TBV-DETAIL-BTN BEGIN */
    '<a href="#" id="tbv-btn-retroview" hidden title="Voir une periode anterieure" style="display:inline-flex;align-items:center;gap:6px;border:1px solid #d32f2f;background:#fff;color:#d32f2f;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;text-decoration:none"><svg viewBox="0 0 24 24" style="width:16px;height:16px" aria-hidden="true"><path fill="currentColor" d="M13 3a9 9 0 0 0-9 9H1l4 4 4-4H6a7 7 0 1 1 7 7v2A9 9 0 1 0 13 3zm-1 5v5l4 2 .75-1.25L13 12.25V8h-1z"/></svg><span>Retroview</span></a>'+
    '<span class="tbv-active-row" id="tbv-active-row" style="display:none;align-items:center;gap:8px;font-size:12px;font-weight:600;color:#d32f2f"><span>RETROVIEW : <span id="tbv-active-stamp"></span></span><button type="button" id="tbv-clear-btn" title="Quitter la retroview" aria-label="Quitter" style="border:none;background:transparent;color:#d32f2f;cursor:pointer;font-size:14px;line-height:1;padding:2px 4px">&#10005;</button></span>'+
    /* TBV-DETAIL-BTN END */
  '</div>';
}
function fmtDurTl(hours) {
  if (hours >= 1) {
    var h = Math.floor(hours);
    var m = Math.round((hours - h) * 60);
    if (m === 60) { h++; m = 0; }
    return m === 0 ? (h + ' h') : (h + ' h ' + (m < 10 ? '0' + m : m));
  }
  var mins = Math.round(hours * 60);
  return mins + ' min';
}
function wireTimelineBar(){
  var root = document.getElementById('u-timeline');
  if (!root) return;
  var btns = root.querySelectorAll('.u-tl-btn');
  var slider = root.querySelector('.u-tl-slider');
  var label = root.querySelector('.u-tl-label');
  if (!btns || !slider || !label) return;
  function getButtonH(){ var v = parseInt(sessionStorage.getItem('tduo.timeline.buttonH') || '24', 10); return (isNaN(v)||v<=0)?24:v; }
  function getZoom(){ var v = parseInt(sessionStorage.getItem('tduo.timeline.zoomPct') || '100', 10); if (isNaN(v)||v<TL_MIN_ZOOM) v=TL_MIN_ZOOM; if (v>100) v=100; return v; }
  function refresh(){
    var btn = getButtonH(), zoom = getZoom(), effH = btn * zoom / 100;
    Array.prototype.forEach.call(btns, function(b){
      var on = parseInt(b.dataset.h, 10) === btn;
      b.style.background = on ? '#5c6bc0' : '#f5f5f5';
      b.style.color = on ? '#fff' : '#333';
      b.style.borderColor = on ? '#5c6bc0' : '#ddd';
    });
    if (parseInt(slider.value, 10) !== zoom) slider.value = zoom;
    label.innerHTML = 'Vue : <strong>' + fmtDurTl(effH) + '</strong> / ' + btn + ' h';
  }
  function refetchNow(){
    if (window.__tbHeatUnified && typeof window.__tbHeatUnified.refetch === 'function') window.__tbHeatUnified.refetch();
  }
  Array.prototype.forEach.call(btns, function(b){
    if (b.__wired) return; b.__wired = true;
    b.addEventListener('click', function(){
      sessionStorage.setItem('tduo.timeline.buttonH', '' + parseInt(b.dataset.h, 10));
      refresh(); refetchNow();
    });
  });
  if (!slider.__wired) {
    slider.__wired = true;
    slider.addEventListener('input', function(){
      sessionStorage.setItem('tduo.timeline.zoomPct', '' + parseInt(slider.value, 10));
      refresh(); refetchNow();
    });
  }
  refresh();
}

var html = '<div class="u-root">'+
  '<div id="u-banner" class="u-err" style="display:none"></div>'+
  '<div class="u-scroll">'+
    '<div style="font-size:16px;font-weight:700;color:#333;text-transform:uppercase;letter-spacing:1px;margin:0 0 8px">Départ chauffage</div>'+
    '<div class="u-tl" id="u-timeline">'+buildTimelineBar()+'</div>'+
    '<div style="display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start">'+
      '<div class="u-card" style="flex:1 1 320px;min-width:280px;max-width:480px;padding:12px 14px"><div id="u-calo"></div><div id="u-err-caloinfo"></div></div>'+
      '<div style="flex:1 1 360px;min-width:300px;display:flex;flex-direction:column">'+chartCard(HEAT_CHART)+'</div>'+
    '</div>'+
  '</div></div>';

// =====================================================================================
// [E] setTimeout + responsive
// =====================================================================================
function wireResponsiveGrid(){
  var grids = document.querySelectorAll('.u-grid');
  function apply(){ var w = (document.querySelector('.u-scroll')||{}).clientWidth || 1000;
    var cols = w < 600 ? '1fr' : '1fr 1fr';
    grids.forEach(function(g){ g.style.gridTemplateColumns = cols; }); if(window.__tbHeatUnified.onResize) window.__tbHeatUnified.onResize(); }
  apply();
  var ro = (typeof ResizeObserver !== 'undefined') ? new ResizeObserver(apply) : null;
  var sc = document.querySelector('.u-scroll'); if(ro && sc) ro.observe(sc);
  window.__tbHeatUnified.ro = ro;
}
setTimeout(function(){
  var prev = window.__tbHeatUnified || {};
  if (prev.timer) clearInterval(prev.timer);
  if (prev.ro) { try{ prev.ro.disconnect(); }catch(e){} }
  if (prev.listeners) Object.keys(prev.listeners).forEach(function(k){ try { document.removeEventListener('mousemove', prev.listeners[k]); } catch(e){} });
  window.__tbHeatUnified = { vis:{}, listeners:{} };
  try { wireResponsiveGrid(); } catch(e){ console.warn('[unified] responsive', e); }
  try { wireTimelineBar(); } catch(e){ console.warn('[unified] timeline', e); }
  startSharedLoop();


  // Retroview applique (sans reload) -> rafraichir charts + donut. Une seule fois.
  if (!window.__tbUnifiedRetroWired) {
    window.__tbUnifiedRetroWired = true;
    window.addEventListener('tduo:retroview', function(){
      if (window.__tbHeatUnified && typeof window.__tbHeatUnified.refetchAll === 'function') window.__tbHeatUnified.refetchAll();
      else if (window.__tbHeatUnified && typeof window.__tbHeatUnified.refetch === 'function') window.__tbHeatUnified.refetch();
      if (typeof window.__renderUsage === 'function') { try { window.__renderUsage(); } catch(e){} }
    });
  }
}, 60);

// =====================================================================================
// [J] RETROVIEW control (porte de pac_info.fn.js /* TBV-DETAIL JS */)
// Le picker vit dans <body> et injecte son CSS dans <head> (survit au cycle de rendu TB).
// =====================================================================================
setTimeout(function(){
  /* TBV-DETAIL JS BEGIN */
  (function(){
    function tok(){ return localStorage.getItem('jwt_token'); }
    function H(){ return { 'X-Authorization': 'Bearer ' + tok() }; }
    function pad(n){ return (n<10?'0':'')+n; }
    function fmtTs(ts){
      var d = new Date(ts);
      return pad(d.getDate())+'/'+pad(d.getMonth()+1)+'/'+d.getFullYear()
           +' a '+pad(d.getHours())+':'+pad(d.getMinutes());
    }
    function getAnchor(){
      try { var v = sessionStorage.getItem('tduo.retroview.endTs'); return v ? parseInt(v, 10) : null; } catch(_e) { return null; }
    }
    function setAnchor(ts){
      try {
        if (ts) sessionStorage.setItem('tduo.retroview.endTs', String(ts));
        else sessionStorage.removeItem('tduo.retroview.endTs');
      } catch(_e) {}
    }
    function renderActive(){
      var row = document.getElementById('tbv-active-row');
      if (!row) return;
      var ts = getAnchor();
      if (ts) {
        var st = document.getElementById('tbv-active-stamp');
        if (st) st.textContent = fmtTs(ts);
        row.classList.add('tbv-active');
        row.style.display = 'inline-flex';
      } else {
        row.classList.remove('tbv-active');
        row.style.display = 'none';
      }
    }
    function maybeReveal(){
      var btn = document.getElementById('tbv-btn-retroview');
      if (!btn || !tok()) return;
      fetch('/api/auth/user', { headers: H() })
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(me){
          if (!me) return;
          if (me.authority === 'TENANT_ADMIN' || me.authority === 'SYS_ADMIN') { btn.hidden = false; return; }
          if (me.authority !== 'CUSTOMER_USER') return;
          fetch('/api/plugins/telemetry/USER/' + me.id.id + '/values/attributes/SERVER_SCOPE?keys=is_admin,access_retroview', { headers: H() })
            .then(function(r){ return r.ok ? r.json() : []; })
            .then(function(attrs){
              var has = (attrs || []).reduce(function(acc, a){ acc[a.key] = a.value; return acc; }, {});
              if (has.is_admin === true || has.access_retroview === true) btn.hidden = false;
            }).catch(function(){});
        }).catch(function(){});
    }
    function openModal(){
      if (window.__tbvPicker && typeof window.__tbvPicker.open === 'function') {
        window.__tbvPicker.open();
      }
    }
    function clearRetroview(){
      setAnchor(null);
      try { window.dispatchEvent(new CustomEvent('tduo:retroview', { detail: null })); } catch(_e) {}
      location.reload();
    }

    // === TBV body-level picker bootstrap ===========================================
    if (!window.__tbvPicker || !window.__tbvPicker.overlay || !document.body.contains(window.__tbvPicker.overlay)) {
        document.querySelectorAll('#tbv-modal-overlay, .tbv-modal-overlay').forEach(function(el) { try { el.remove(); } catch(_e) {} });
        (function() {
            var P = {};
            P.state = { viewYear:0, viewMonth:0, selYear:0, selMonth:0, selDay:0, selHour:0, selMinute:0 };
            var MONTHS = ['janvier','fevrier','mars','avril','mai','juin','juillet','aout','septembre','octobre','novembre','decembre'];
            function pad(n) { return n < 10 ? '0' + n : '' + n; }

            if (!document.getElementById('tbvp-styles')) {
                var st = document.createElement('style');
                st.id = 'tbvp-styles';
                st.textContent = ''
                    + '.tbvp-overlay { position:fixed; inset:0; background:rgba(0,0,0,0.45); display:flex; align-items:center; justify-content:center; z-index:100000; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }'
                    + '.tbvp-overlay[hidden] { display:none !important; }'
                    + '.tbvp-modal { background:#fff; border-radius:12px; padding:20px 22px 16px; width:min(520px,94vw); box-shadow:0 12px 40px rgba(0,0,0,0.25); box-sizing:border-box; }'
                    + '.tbvp-title { font-size:14px; font-weight:500; color:#444; margin-bottom:10px; }'
                    + '.tbvp-field { display:flex; align-items:center; gap:10px; padding:12px 14px; border:2px solid #d32f2f; border-radius:6px; margin-bottom:18px; cursor:default; }'
                    + '.tbvp-field-icon { color:#d32f2f; font-size:16px; }'
                    + '.tbvp-field-text { flex:1; color:#333; font-size:14px; font-variant-numeric:tabular-nums; }'
                    + '.tbvp-field-cal { color:#888; font-size:18px; }'
                    + '.tbvp-body { display:flex; gap:14px; align-items:flex-start; }'
                    + '.tbvp-cal { flex:1 1 auto; min-width:0; }'
                    + '.tbvp-cal-header { display:flex; align-items:center; padding:4px 0 6px; }'
                    + '.tbvp-cal-title { flex:1; font-size:14px; color:#333; font-weight:500; }'
                    + '.tbvp-cal-nav { width:28px; height:28px; border:none; background:transparent; cursor:pointer; font-size:18px; color:#666; border-radius:50%; line-height:1; padding:0; }'
                    + '.tbvp-cal-nav:hover { background:#f5f5f5; }'
                    + '.tbvp-cal-dow { display:grid; grid-template-columns:repeat(7,1fr); text-align:center; font-size:11px; color:#888; padding:4px 0; font-weight:500; }'
                    + '.tbvp-cal-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:2px; }'
                    + '.tbvp-cal-day { aspect-ratio:1; display:flex; align-items:center; justify-content:center; font-size:13px; color:#333; border-radius:50%; cursor:pointer; user-select:none; transition:background .12s; }'
                    + '.tbvp-cal-day:hover:not(.tbvp-cal-disabled):not(.tbvp-cal-selected) { background:#ffebee; }'
                    + '.tbvp-cal-day.tbvp-cal-other { color:#ccc; }'
                    + '.tbvp-cal-day.tbvp-cal-today { color:#d32f2f; font-weight:700; }'
                    + '.tbvp-cal-day.tbvp-cal-selected { background:#d32f2f; color:#fff; font-weight:600; }'
                    + '.tbvp-cal-day.tbvp-cal-disabled { color:#ddd; cursor:not-allowed; }'
                    + '.tbvp-times { display:flex; gap:8px; align-self:stretch; }'
                    + '.tbvp-time-col { display:flex; flex-direction:column; height:240px; overflow-y:auto; scrollbar-width:thin; padding:0 2px; min-width:46px; }'
                    + '.tbvp-time-col::-webkit-scrollbar { width:4px; }'
                    + '.tbvp-time-col::-webkit-scrollbar-thumb { background:#ddd; border-radius:2px; }'
                    + '.tbvp-time-col::-webkit-scrollbar-track { background:transparent; }'
                    + '.tbvp-time-item { padding:5px 10px; font-size:15px; color:#888; cursor:pointer; border-radius:18px; text-align:center; margin:1px 0; font-variant-numeric:tabular-nums; }'
                    + '.tbvp-time-item:hover { background:#ffebee; color:#333; }'
                    + '.tbvp-time-item.tbvp-time-selected { background:#d32f2f; color:#fff; font-weight:600; }'
                    + '.tbvp-actions { display:flex; justify-content:flex-end; gap:4px; margin-top:14px; }'
                    + '.tbvp-btn { background:transparent; border:none; padding:8px 16px; font-size:14px; font-weight:600; cursor:pointer; border-radius:4px; letter-spacing:0.5px; text-transform:uppercase; }'
                    + '.tbvp-cancel { color:#666; }'
                    + '.tbvp-cancel:hover { background:#f5f5f5; }'
                    + '.tbvp-ok { background:#d32f2f; color:#fff; padding:8px 24px; }'
                    + '.tbvp-ok:hover { background:#b71c1c; }'
                    // active-row display rules (etaient dans pac_info.css)
                    + '#tbv-active-row { display:none; }'
                    + '#tbv-active-row.tbv-active { display:inline-flex; }';
                document.head.appendChild(st);
            }

            var ov = document.createElement('div');
            ov.className = 'tbvp-overlay';
            ov.hidden = true;
            ov.innerHTML = ''
                + '<div class="tbvp-modal" role="dialog" aria-modal="true" aria-label="Choisir une date anterieure">'
                +   '<div class="tbvp-title">Visualisez les donnees a une date anterieure</div>'
                +   '<div class="tbvp-field">'
                +     '<span class="tbvp-field-icon">&#128269;</span>'
                +     '<span class="tbvp-field-text"></span>'
                +     '<span class="tbvp-field-cal">&#128197;</span>'
                +   '</div>'
                +   '<div class="tbvp-body">'
                +     '<div class="tbvp-cal">'
                +       '<div class="tbvp-cal-header">'
                +         '<span class="tbvp-cal-title"></span>'
                +         '<button type="button" class="tbvp-cal-nav tbvp-cal-prev" aria-label="Mois precedent">&lsaquo;</button>'
                +         '<button type="button" class="tbvp-cal-nav tbvp-cal-next" aria-label="Mois suivant">&rsaquo;</button>'
                +       '</div>'
                +       '<div class="tbvp-cal-dow"><span>L</span><span>M</span><span>M</span><span>J</span><span>V</span><span>S</span><span>D</span></div>'
                +       '<div class="tbvp-cal-grid"></div>'
                +     '</div>'
                +     '<div class="tbvp-times">'
                +       '<div class="tbvp-time-col tbvp-time-h"></div>'
                +       '<div class="tbvp-time-col tbvp-time-m"></div>'
                +     '</div>'
                +   '</div>'
                +   '<div class="tbvp-actions">'
                +     '<button type="button" class="tbvp-btn tbvp-cancel">Annuler</button>'
                +     '<button type="button" class="tbvp-btn tbvp-ok">OK</button>'
                +   '</div>'
                + '</div>';
            document.body.appendChild(ov);
            P.overlay = ov;

            var elTitle = ov.querySelector('.tbvp-cal-title');
            var elGrid  = ov.querySelector('.tbvp-cal-grid');
            var elHCol  = ov.querySelector('.tbvp-time-h');
            var elMCol  = ov.querySelector('.tbvp-time-m');
            var elField = ov.querySelector('.tbvp-field-text');

            P.renderCal = function() {
                var s = P.state;
                elTitle.textContent = MONTHS[s.viewMonth] + ' ' + s.viewYear;
                var first       = new Date(s.viewYear, s.viewMonth, 1);
                var firstDow    = (first.getDay() + 6) % 7;
                var daysInMonth = new Date(s.viewYear, s.viewMonth + 1, 0).getDate();
                var prevDays    = new Date(s.viewYear, s.viewMonth, 0).getDate();
                var today       = new Date(); today.setHours(0,0,0,0);
                var todayTs     = today.getTime();
                var nowTs       = Date.now();
                elGrid.innerHTML = '';
                var cells = [];
                for (var i = 0; i < firstDow; i++) {
                    cells.push({ y: s.viewMonth === 0 ? s.viewYear - 1 : s.viewYear, m: (s.viewMonth + 11) % 12, d: prevDays - firstDow + 1 + i, other: true });
                }
                for (var i = 1; i <= daysInMonth; i++) {
                    cells.push({ y: s.viewYear, m: s.viewMonth, d: i, other: false });
                }
                while (cells.length < 42) {
                    var k = cells.length - firstDow - daysInMonth;
                    cells.push({ y: s.viewMonth === 11 ? s.viewYear + 1 : s.viewYear, m: (s.viewMonth + 1) % 12, d: k + 1, other: true });
                }
                cells.forEach(function(c) {
                    var el = document.createElement('div');
                    el.className = 'tbvp-cal-day' + (c.other ? ' tbvp-cal-other' : '');
                    var cellTs = new Date(c.y, c.m, c.d).getTime();
                    if (cellTs === todayTs) el.classList.add('tbvp-cal-today');
                    if (c.y === s.selYear && c.m === s.selMonth && c.d === s.selDay) el.classList.add('tbvp-cal-selected');
                    if (cellTs > nowTs) el.classList.add('tbvp-cal-disabled');
                    el.textContent = c.d;
                    el.addEventListener('click', function() {
                        if (el.classList.contains('tbvp-cal-disabled')) return;
                        s.selYear = c.y; s.selMonth = c.m; s.selDay = c.d;
                        s.viewYear = c.y; s.viewMonth = c.m;
                        P.renderCal();
                        P.renderField();
                    });
                    elGrid.appendChild(el);
                });
            };

            function buildCol(col, count, step, selected, key) {
                col.innerHTML = '';
                for (var v = 0; v < count; v += step) {
                    var el = document.createElement('div');
                    el.className = 'tbvp-time-item' + (v === selected ? ' tbvp-time-selected' : '');
                    el.textContent = pad(v);
                    (function(val) {
                        el.addEventListener('click', function() {
                            P.state[key] = val;
                            P.renderTime();
                            P.renderField();
                        });
                    })(v);
                    col.appendChild(el);
                }
                var sel = col.querySelector('.tbvp-time-selected');
                if (sel) {
                    var top = sel.offsetTop - (col.clientHeight - sel.offsetHeight) / 2;
                    col.scrollTop = Math.max(0, top);
                }
            }

            P.renderTime = function() {
                buildCol(elHCol, 24, 1, P.state.selHour,   'selHour');
                buildCol(elMCol, 60, 5, P.state.selMinute, 'selMinute');
            };

            P.renderField = function() {
                var s = P.state;
                elField.textContent = pad(s.selDay) + '/' + pad(s.selMonth + 1) + '/' + s.selYear + '  ' + pad(s.selHour) + ':' + pad(s.selMinute);
            };

            P.open = function() {
                var v = sessionStorage.getItem('tduo.retroview.endTs');
                var ts = v ? parseInt(v, 10) : Date.now();
                if (!ts || isNaN(ts)) ts = Date.now();
                var d = new Date(ts);
                P.state.viewYear  = d.getFullYear();
                P.state.viewMonth = d.getMonth();
                P.state.selYear   = d.getFullYear();
                P.state.selMonth  = d.getMonth();
                P.state.selDay    = d.getDate();
                P.state.selHour   = d.getHours();
                P.state.selMinute = Math.round(d.getMinutes() / 5) * 5;
                if (P.state.selMinute >= 60) { P.state.selMinute = 0; P.state.selHour = (P.state.selHour + 1) % 24; }
                P.renderCal();
                P.renderTime();
                P.renderField();
                ov.hidden = false;
            };

            P.close = function() { ov.hidden = true; };

            P.getTs = function() {
                var s = P.state;
                var d = new Date(s.selYear, s.selMonth, s.selDay, s.selHour, s.selMinute, 0, 0);
                return d.getTime();
            };

            P.apply = function() {
                var ts = P.getTs();
                if (!ts || isNaN(ts)) return;
                try { sessionStorage.setItem('tduo.retroview.endTs', String(ts)); } catch(_e) {}
                try { window.dispatchEvent(new CustomEvent('tduo:retroview', { detail: { endTs: ts } })); } catch(_e) {}
                ov.hidden = true;
                renderActive();
            };

            ov.querySelector('.tbvp-cal-prev').addEventListener('click', function(ev) { ev.preventDefault(); P.state.viewMonth--; if (P.state.viewMonth < 0) { P.state.viewMonth = 11; P.state.viewYear--; } P.renderCal(); });
            ov.querySelector('.tbvp-cal-next').addEventListener('click', function(ev) { ev.preventDefault(); P.state.viewMonth++; if (P.state.viewMonth > 11) { P.state.viewMonth = 0; P.state.viewYear++; } P.renderCal(); });
            ov.querySelector('.tbvp-cancel').addEventListener('click', function(ev) { ev.preventDefault(); P.close(); });
            ov.querySelector('.tbvp-ok').addEventListener('click', function(ev) { ev.preventDefault(); P.apply(); });
            ov.addEventListener('click', function(ev) { if (ev.target === ov) P.close(); });
            document.addEventListener('keydown', function(ev) { if (ev.key === 'Escape' && !ov.hidden) P.close(); });

            window.__tbvPicker = P;
        })();
    }
    // === end TBV body-level picker bootstrap ========================================

    var rb = document.getElementById('tbv-btn-retroview');
    if (rb && !rb.__wired) { rb.__wired = true; rb.addEventListener('click', function(ev){ ev.preventDefault(); openModal(); }); }
    var clr = document.getElementById('tbv-clear-btn');
    if (clr && !clr.__wired) { clr.__wired = true; clr.addEventListener('click', function(ev){ ev.preventDefault(); clearRetroview(); }); }

    maybeReveal();
    renderActive();
  })();
  /* TBV-DETAIL JS END */
}, 200);

// =====================================================================================
// [F] startSharedLoop / renderCharts / renderInfo / safe / showBanner
// =====================================================================================
function startSharedLoop() {
  var DEVICE_ID = resolveDevice();
  if (!DEVICE_ID) { console.warn('[unified] no device'); return; }
  var EVT = { intervals: [], last: 0 };

  function infoEndTs(){ var rv = sessionStorage.getItem('tduo.retroview.endTs'); var t = rv ? parseInt(rv,10) : 0; return (t>0) ? t : Date.now(); }

  function fetchCharts() {
    var win = getTimeWindow();
    var iv = getAggInterval(win);
    var allKeys=[]; HEAT_CHART.series.forEach(function(s){ allKeys.push(s.key); });
    var url = '/api/plugins/telemetry/DEVICE/' + DEVICE_ID +
      '/values/timeseries?keys=pac_v2&startTs=' + win.startTs + '&endTs=' + win.endTs +
      '&interval=' + iv + '&agg=NONE&limit=20000';
    fetch(url, { headers: { 'X-Authorization': 'Bearer ' + getToken() } })
      .then(function(r){ return r.json(); })
      .then(function(resp){
        var seriesData = PACV2_TO_SERIES({pac_v2: resp.pac_v2 || []}, allKeys);
        fetchEvt(DEVICE_ID, win, EVT, function(){ renderCharts(seriesData, win, EVT.intervals); });
        renderCharts(seriesData, win, EVT.intervals);
      })
      .catch(function(e){ showBanner('Erreur de chargement des courbes.'); console.warn('[unified] fetchCharts', e); });
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
        renderInfo(latestFlat);
      })
      .catch(function(e){ console.warn('[unified] fetchInfo', e); });
  }

  window.__tbHeatUnified.refetch = fetchCharts;                 // timeline change -> curves ONLY
  window.__tbHeatUnified.refetchAll = function(){ fetchCharts(); fetchInfo(); };
  fetchCharts(); fetchInfo();
  window.__tbHeatUnified.timer = setInterval(function(){ fetchCharts(); fetchInfo(); }, 30000);
}
function renderCharts(seriesData, win, evt) {
  safe('heat', function(){ renderChart(HEAT_CHART, seriesData, win, evt); });
}
function renderInfo(latestFlat) {
  safe('caloinfo', function(){ var el=document.getElementById('u-calo'); if(el) el.innerHTML=caloInfo(latestFlat); });
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
    window.__tbHeatUnified.vis[cfg.id] = window.__tbHeatUnified.vis[cfg.id] || {};
    var visibility = window.__tbHeatUnified.vis[cfg.id];
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
    var L = window.__tbHeatUnified.listeners = window.__tbHeatUnified.listeners || {};
    if (L[cfg.id]) document.removeEventListener('mousemove', L[cfg.id]);
    L[cfg.id] = onMouseMove;
    document.addEventListener('mousemove', onMouseMove);

    drawChart();
    drawLegend();
}

// =====================================================================================
// [H] table calorimetre (caloInfo) + helpers partages isBad/fv/tH
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

return html;
