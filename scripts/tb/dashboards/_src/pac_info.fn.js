// __PACV2_SHIM__ : remap pac_v2 nested -> flat dict (compat ancien template)
var PACV2_FLATTEN = function(p) {
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
    if (p.dhw) {
        for (var __k in p.dhw) {
            var __v = p.dhw[__k];
            if (__v === null || __v === undefined) continue;
            var __m = __k.match(/^pump([1-4])$/);
            if (__m && typeof __v === 'object') {
                for (var __k2 in __v) out['dhw_pump' + __m[1] + '_' + __k2] = __v[__k2];
            } else if (typeof __v !== 'object') {
                out['dhw_' + __k] = __v;
            }
        }
    }
    if (p.heat) {
        for (var __k in p.heat) {
            var __v = p.heat[__k];
            if (__v === null || __v === undefined) continue;
            if (__k === 'calo' && typeof __v === 'object') {
                for (var __k2 in __v) out['heat_calo_' + __k2] = __v[__k2];
            } else if (typeof __v !== 'object') {
                out['heat_' + __k] = __v;
            }
        }
    }
    if (p.caloM) {
        for (var __k in p.caloM) {
            var __v = p.caloM[__k];
            if (__v !== null && __v !== undefined && typeof __v !== 'object') out['caloM_' + __k] = __v;
        }
    }
    ['pump1M', 'pump2M'].forEach(function(__name) {
        if (p[__name]) {
            for (var __k in p[__name]) {
                var __v = p[__name][__k];
                if (__v !== null && __v !== undefined && typeof __v !== 'object') out[__name + '_' + __k] = __v;
            }
        }
    });
    return out;
};
(function() {
    // __PACV2_RETROVIEW_SHIM__ : respecter le mode retroview
    var __ds = (data && data[0]) || null;
    if (!__ds) return;
    var __pv = null;

    // 1. Si retroview actif : fetch sync a sessionStorage.tduo.retroview.endTs
    try {
        var __rvEndTs = sessionStorage.getItem('tduo.retroview.endTs');
        if (__rvEndTs) {
            var __ctxRef = (typeof ctx !== 'undefined' && ctx) ? ctx
                          : (typeof self !== 'undefined' && self.ctx ? self.ctx : null);
            var __ds0 = (__ctxRef && __ctxRef.datasources && __ctxRef.datasources[0]) || null;
            var __devId = __ds0 && (__ds0.entityId || (__ds0.entity && __ds0.entity.id && __ds0.entity.id.id));
            if (__devId) {
                var __end = parseInt(__rvEndTs, 10);
                var __url = '/api/plugins/telemetry/DEVICE/' + __devId +
                            '/values/timeseries?keys=pac_v2&startTs=0&endTs=' + __end +
                            '&limit=1&orderBy=DESC&agg=NONE';
                var __token = localStorage.getItem('jwt_token');
                var __xhr = new XMLHttpRequest();
                __xhr.open('GET', __url, false);
                if (__token) __xhr.setRequestHeader('X-Authorization', 'Bearer ' + __token);
                try {
                    __xhr.send();
                    if (__xhr.status === 200) {
                        var __resp = JSON.parse(__xhr.responseText);
                        if (__resp.pac_v2 && __resp.pac_v2.length) {
                            var __raw = __resp.pac_v2[0].value;
                            __pv = (typeof __raw === 'string') ? JSON.parse(__raw) : __raw;
                        }
                    }
                } catch (e) {}
            }
        }
    } catch (e) {}

    // 2. Fallback : data[0] live (mode normal)
    if (!__pv) {
        __pv = __ds.pac_v2;
        if (typeof __pv === 'string') { try { __pv = JSON.parse(__pv); } catch(_) { __pv = null; } }
    }

    if (__pv) { data = [PACV2_FLATTEN(__pv)]; }
})();

var e = data[0] || {};
var ctxRef = (typeof ctx !== 'undefined' && ctx) ? ctx : (typeof self !== 'undefined' ? self.ctx : null);
var sp = (ctxRef && ctxRef.stateController) ? (ctxRef.stateController.getStateParams() || {}) : {};
var idx = sp.hpIndex || sp.hp || 1;
var prefix = 'HP' + idx + '_';
var DID = '0964da30-3e56-11f1-bbfe-e1395562cba0';

function isBad(val) {
    if (val === null || val === undefined || val === '') return true;
    var n = parseFloat(val);
    // Sentinelles firmware: -99.9 (sonde déconnectée) ET -47.8
    // (code de défaut). Aucune sonde HVAC réelle ne descend sous -45 °C.
    return isNaN(n) || n <= -45;
}
function fv(val, unit, decimals) {
    if (isBad(val)) return '--';
    return parseFloat(val).toFixed(decimals !== undefined ? decimals : 1) + (unit || '');
}
function needleAngle(val, min, max) {
    var v = Math.max(min, Math.min(max, parseFloat(val) || min));
    return -135 + ((v - min) / (max - min)) * 270;
}
function buildGauge(id, label, value, tempLabel, tempValue, min, max, color, colorLight) {
    var valid = !isBad(value);
    var angle = valid ? needleAngle(value, min, max) : -135;
    var valDisp = fv(value, '', 1);
    var tempDisp = fv(tempValue, '°C', 1);
    var ticks = '';
    for (var i = 0; i <= 10; i++) {
        var a = -135 + (i * 27), rad = a * Math.PI / 180;
        var lv = Math.round(min + (i / 10) * (max - min));
        var x1 = 100 + Math.sin(rad)*75, y1 = 100 - Math.cos(rad)*75;
        var x2 = 100 + Math.sin(rad)*85, y2 = 100 - Math.cos(rad)*85;
        var xt = 100 + Math.sin(rad)*62, yt = 100 - Math.cos(rad)*62;
        ticks += '<line x1="'+x1+'" y1="'+y1+'" x2="'+x2+'" y2="'+y2+'" stroke="#555" stroke-width="1.5"/>';
        ticks += '<text x="'+xt+'" y="'+(yt+4)+'" text-anchor="middle" font-size="10" fill="#555">'+lv+'</text>';
    }
    return '<div class="gauge-block">' +
        '<div class="gauge-title">'+label+'</div>' +
        '<div class="gauge-center">' +
            '<svg viewBox="0 0 200 200" class="gauge-svg" preserveAspectRatio="xMidYMid meet">' +
                '<defs><radialGradient id="gradBg_'+id+'" cx="50%" cy="50%" r="50%">' +
                    '<stop offset="0%" stop-color="#fff"/><stop offset="100%" stop-color="'+colorLight+'"/>' +
                '</radialGradient></defs>' +
                '<circle cx="100" cy="100" r="95" fill="url(#gradBg_'+id+')" stroke="#ccc" stroke-width="2"/>' +
                ticks +
                '<g transform="rotate('+angle+' 100 100)"><line x1="100" y1="100" x2="100" y2="30" stroke="'+(valid?color:'#9E9E9E')+'" stroke-width="3" stroke-linecap="round"/></g>' +
                '<circle cx="100" cy="100" r="8" fill="#333"/>' +
                '<text x="100" y="140" text-anchor="middle" font-size="12" fill="#666">bar</text>' +
                '<rect x="55" y="152" width="90" height="26" fill="#222" rx="4"/>' +
                '<text x="100" y="170" text-anchor="middle" font-size="14" font-weight="bold" fill="#ff6b6b" font-family="monospace">'+valDisp+'</text>' +
            '</svg>' +
            '<div class="temp-box">' +
                '<div class="temp-label">'+tempLabel+'</div>' +
                '<div class="temp-value">'+tempDisp+'</div>' +
            '</div>' +
        '</div>' +
    '</div>';
}
function buildValueRow(label, value, unit, decimals) {
    return '<div class="val-row"><span class="val-label">'+label+'</span><span class="val-value">'+fv(value,unit,decimals)+'</span></div>';
}

var html = '<div class="md-body">';
html += '<nav class="md-nav">';
// __PACINFO_NAV_BTNS_REMOVED_V1__ : Accueil removed (now in unified navbar)
// __PACINFO_NAV_BTNS_REMOVED_V1__ : Retour removed (now in unified navbar)
/* TBV-DETAIL-BTN BEGIN */
html += '<a href="#" id="tbv-btn-retroview" class="back-btn back-btn-retroview" hidden title="Voir une période antérieure (24 h se finissant à l\'instant choisi)"><svg class="nav-svg-icon" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M13 3a9 9 0 0 0-9 9H1l4 4 4-4H6a7 7 0 1 1 7 7v2A9 9 0 1 0 13 3zm-1 5v5l4 2 .75-1.25L13 12.25V8h-1z"/></svg><span class="back-label">Rétroview</span></a>';
html += '<span class="tbv-active-row" id="tbv-active-row"><span class="tbv-active-label">RÉTROVIEW : <span id="tbv-active-stamp"></span></span><button type="button" class="tbv-clear" id="tbv-clear-btn" title="Quitter la rétroview" aria-label="Quitter">✕</button></span>';
/* TBV-DETAIL-BTN END */

html += '</nav>';
html += '<div class="pac-detail-frame">';
html += '<div class="frame-header">';
var _entName = (data[0] && data[0].entityName) || '';
html += '<h2 class="pac-hybride-title">PAC Hybride n'+idx+'</h2>'; // __PAC_INFO_TITLE_RESTYLED__
if (_entName) html += '<div class="frame-install-sub">N° '+_entName+'</div>';
html += '<div class="frame-date" id="frame-date-val">'+(e['date']||'')+' '+(e['time']||'')+'</div>';
html += '</div>';
html += '<div class="pac-top-row">';
html += buildGauge('hp','Pression HP',e[prefix+'pHi'],'T cond',e[prefix+'tCond'],-5,35,'#c62828','#ffebee');
html += buildGauge('bp','Pression BP',e[prefix+'pLo'],'T evap',e[prefix+'tEvap'],-5,25,'#1976d2','#e3f2fd');
html += '<div class="values-block">';
html += buildValueRow('Fréquence compresseur',e[prefix+'invert_freq'],' Hz',1);
html += buildValueRow('Puissance compresseur',e[prefix+'invert_pwr'],' W',0);
html += buildValueRow('Vitesse ventilateur',e[prefix+'rpm'],' rpm',0);
html += buildValueRow('Position détendeur',e[prefix+'dpf'],'',0);
html += buildValueRow('T° surchauffe',e[prefix+'tOH'],'°C',1);
/* TBN-TIME-UNIT-BEGIN */
var __tUnit = 'seconds';
function tH(v) {
  if (v === null || v === undefined || v === '') return v;
  var n = Number(v);
  if (!isFinite(n)) return v;
  return __tUnit === 'seconds' ? (n / 3600) : n;
}
/* TBN-TIME-UNIT-END */
html += buildValueRow('Temps de fonctionnement',tH(e[prefix+'time']),' h',0);
html += '</div>';
html += '</div>';
html += '</div>';
html += '</div>';

// Reecrit le bandeau TB (TB n'interpole pas ${hpIndex} dans name) via
// TreeWalker sur tous les documents accessibles (widget peut tourner en iframe).
function updateStateBanner(targetText) {
    if (window.__tduoBannerIv) { clearInterval(window.__tduoBannerIv); }

    var docs = [document];
    try { if (window.parent && window.parent.document && window.parent.document !== document) docs.push(window.parent.document); } catch (e) {}
    try { if (window.top && window.top.document && docs.indexOf(window.top.document) < 0) docs.push(window.top.document); } catch (e) {}

    // Matche : "Données PAC", "Données PAC N", "Données PAC ${hpIndex}",
    // "Données détaillées PAC", "Données Détaillés PAC N" (toutes variantes)
    var rx = /^Donn[ée]es(\s+[Dd][ée]taill[eé]{1,2}s)?\s*PAC(\s+\d+|\s*\$\{hpIndex\})?\s*$/i;

    // Skip les text nodes appartenant au contenu du widget lui-meme (le h2
    // "Données PAC N" doit rester tel quel — on ne patche que le bandeau TB).
    function isInsideWidget(node) {
        var el = node.parentElement;
        while (el) {
            if (el.classList && (el.classList.contains('pac-detail-frame') ||
                                 el.classList.contains('md-nav'))) return true;
            el = el.parentElement;
        }
        return false;
    }

    function tryUpdate() {
        var found = false;
        for (var d = 0; d < docs.length; d++) {
            try {
                var body = docs[d].body;
                if (!body) continue;
                var walker = docs[d].createTreeWalker(body, NodeFilter.SHOW_TEXT, null);
                var node;
                while ((node = walker.nextNode())) {
                    var t = (node.nodeValue || '').trim();
                    if (!t || t === targetText) continue;
                    if (isInsideWidget(node)) continue;
                    if (rx.test(t)) {
                        node.nodeValue = targetText;
                        found = true;
                    }
                }
            } catch (e) {}
        }
        return found;
    }

    tryUpdate();
    var attempts = 0;
    window.__tduoBannerIv = setInterval(function() {
        attempts++;
        tryUpdate();
        if (attempts > 30) { clearInterval(window.__tduoBannerIv); window.__tduoBannerIv = null; }
    }, 200);
}
updateStateBanner('Données détaillées PAC ' + idx);

setTimeout(function() {
    // Remove any previously injected customer-chrome-hiding stylesheet
    var _prev = document.getElementById('tb-customer-fullscreen-style');
    if (_prev) _prev.parentNode.removeChild(_prev);

    function _currentEntityId() {
        try {
            var raw = new URL(window.location.href).searchParams.get('state');
            if (!raw) return null;
            var arr = JSON.parse(atob(decodeURIComponent(raw)));
            for (var i = arr.length - 1; i >= 0; i--) {
                var p = arr[i] && arr[i].params;
                if (p && p.entityId && p.entityId.id) return p.entityId;
            }
        } catch (e) {}
        return null;
    }

    function _goToState(stateId) {
        // 'menu' is the dashboard root — no entity needed.
        // For 'default' (and any other entity-bound state) we have to
        // forward the current entityId, otherwise the alias
        // 'Chaufferie sélectionnée' falls back to defaultStateEntity (Yahtec).
        var params = {};
        if (stateId !== 'menu') {
            var eid = _currentEntityId();
            if (eid) params.entityId = eid;
        }
        var stateB64 = btoa(JSON.stringify([{ id: stateId, params: params }]));
        window.history.pushState({}, '', window.location.pathname + '?state=' + encodeURIComponent(stateB64));
        var evt = document.createEvent('Event');
        evt.initEvent('popstate', true, true);
        window.dispatchEvent(evt);
    }

    var homeBtn = document.getElementById('nav-home-btn');
    if (homeBtn && !homeBtn.__wired) {
        homeBtn.__wired = true;
        homeBtn.addEventListener('click', function(ev) {
            ev.preventDefault();
            _goToState('menu');
        });
    }

    var backBtn = document.getElementById('nav-back-btn');
    if (backBtn && !backBtn.__wired) {
        backBtn.__wired = true;
        backBtn.addEventListener('click', function(ev) {
            ev.preventDefault();
            _goToState('default');
        });
    }
}, 100);


/* TBV-DETAIL-MODAL: removed — picker now lives in <body> via window.__tbvPicker */

    setTimeout(function(){

    /* TBV-DETAIL JS BEGIN */
    (function(){
      function tok(){ return localStorage.getItem('jwt_token'); }
      function H(){ return { 'X-Authorization': 'Bearer ' + tok() }; }
      function pad(n){ return (n<10?'0':'')+n; }
      function fmtTs(ts){
        var d = new Date(ts);
        return pad(d.getDate())+'/'+pad(d.getMonth()+1)+'/'+d.getFullYear()
             +' à '+pad(d.getHours())+':'+pad(d.getMinutes());
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
        } else {
          row.classList.remove('tbv-active');
        }
      }
      function maybeReveal(){
        var btn = document.getElementById('tbv-btn-retroview');
        if (!btn || !tok()) return;
        fetch('/api/auth/user', { headers: H() })
          .then(function(r){ return r.ok ? r.json() : null; })
          .then(function(me){
            if (!me) return;
            if (me.authority === 'TENANT_ADMIN') { btn.hidden = false; return; }
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
      function closeModal(){ if (window.__tbvPicker) window.__tbvPicker.close(); }
      function readModalTs(){ return window.__tbvPicker ? window.__tbvPicker.getTs() : null; }
      function refreshPreview(){ /* handled by new picker */ }
      
      function applyRetroview(){ if (window.__tbvPicker) window.__tbvPicker.apply(); }
      function clearRetroview(){
        setAnchor(null);
        try { window.dispatchEvent(new CustomEvent('tduo:retroview', { detail: null })); } catch(_e) {}
        location.reload();
      }
      
      // === TBV body-level picker bootstrap ===========================================
      // Build a global retroview picker once per page load. It lives directly in
      // <body>, so the widget render cycle cannot destroy it.
      if (!window.__tbvPicker || !window.__tbvPicker.overlay || !document.body.contains(window.__tbvPicker.overlay)) {
          // Strip stale modals left over from previous in-widget implementations
          document.querySelectorAll('#tbv-modal-overlay, .tbv-modal-overlay').forEach(function(el) { try { el.remove(); } catch(_e) {} });
          (function() {
              var P = {};
              P.state = { viewYear:0, viewMonth:0, selYear:0, selMonth:0, selDay:0, selHour:0, selMinute:0 };
              var MONTHS = ['janvier','fevrier','mars','avril','mai','juin','juillet','aout','septembre','octobre','novembre','decembre'];
              function pad(n) { return n < 10 ? '0' + n : '' + n; }

              // CSS — injected once into <head>. No @media (TB cssjs may swallow it
              // anyway; here it doesn't go through cssjs since it's appended to head,
              // but stay defensive).
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
                      + '.tbvp-ok:hover { background:#b71c1c; }';
                  document.head.appendChild(st);
              }

              // Modal HTML — built programmatically
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
                  // Scroll selected into view (centered)
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
                  // Local-time construction (timezone-correct)
                  var d = new Date(s.selYear, s.selMonth, s.selDay, s.selHour, s.selMinute, 0, 0);
                  return d.getTime();
              };

              P.apply = function() {
                  var ts = P.getTs();
                  if (!ts || isNaN(ts)) return;
                  try { sessionStorage.setItem('tduo.retroview.endTs', String(ts)); } catch(_e) {}
                  try { window.dispatchEvent(new CustomEvent('tduo:retroview', { detail: { endTs: ts } })); } catch(_e) {}
                  ov.hidden = true;
                  location.reload();
              };

              // Wire buttons + nav
              ov.querySelector('.tbvp-cal-prev').addEventListener('click', function(ev) { ev.preventDefault(); P.state.viewMonth--; if (P.state.viewMonth < 0) { P.state.viewMonth = 11; P.state.viewYear--; } P.renderCal(); });
              ov.querySelector('.tbvp-cal-next').addEventListener('click', function(ev) { ev.preventDefault(); P.state.viewMonth++; if (P.state.viewMonth > 11) { P.state.viewMonth = 0; P.state.viewYear++; } P.renderCal(); });
              ov.querySelector('.tbvp-cancel').addEventListener('click', function(ev) { ev.preventDefault(); P.close(); });
              ov.querySelector('.tbvp-ok').addEventListener('click', function(ev) { ev.preventDefault(); P.apply(); });
              // Click outside to close
              ov.addEventListener('click', function(ev) { if (ev.target === ov) P.close(); });
              // ESC to close
              document.addEventListener('keydown', function(ev) { if (ev.key === 'Escape' && !ov.hidden) P.close(); });

              window.__tbvPicker = P;
          })();
      }
      // === end TBV body-level picker bootstrap ========================================

      
      var rb = document.getElementById('tbv-btn-retroview');
      if (rb && !rb.__wired) { rb.__wired = true; rb.addEventListener('click', function(ev){ ev.preventDefault(); openModal(); }); }
      var cancel = document.getElementById('tbv-btn-cancel');
      if (cancel && !cancel.__wired) { cancel.__wired = true; cancel.addEventListener('click', function(ev){ ev.preventDefault(); closeModal(); }); }
      var apply = document.getElementById('tbv-btn-apply');
      if (apply && !apply.__wired) { apply.__wired = true; apply.addEventListener('click', function(ev){ ev.preventDefault(); applyRetroview(); }); }
      var clr = document.getElementById('tbv-clear-btn');
      if (clr && !clr.__wired) { clr.__wired = true; clr.addEventListener('click', function(ev){ ev.preventDefault(); clearRetroview(); }); }
      ['tbv-input-date','tbv-input-time'].forEach(function(id){
        var el = document.getElementById(id);
        if (el && !el.__wired) { el.__wired = true; el.addEventListener('input', refreshPreview); }
      });
      var ov = document.getElementById('tbv-modal-overlay');
      if (ov && !ov.__wired) {
        ov.__wired = true;
        ov.addEventListener('click', function(ev){ if (ev.target === ov) closeModal(); });
      }
      if (!window.__tbvKeydownWired) {
        window.__tbvKeydownWired = true;
        document.addEventListener('keydown', function(ev){
          if (ev.key === 'Escape') {
            var ov = document.getElementById('tbv-modal-overlay');
            if (ov && !ov.hidden) closeModal();
          }
        });
      }

      maybeReveal();
      renderActive();
    })();
    /* TBV-DETAIL JS END */

}, 200);
    return html;