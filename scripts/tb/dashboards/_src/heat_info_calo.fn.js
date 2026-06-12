// __HEAT_STATE_V1__ Chauffage Info (derive de PAC Info)
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

html += '<div class="pac-detail-frame">';
// Tableau calorimetre chauffage (heat.calo.* aplati en heat_calo_*)
// __CALO_UNITS_V2__ : codes unite Modbus Mainone (doc V0.7), facteur applique
var CALO_UNITS = {
    2875: { m: 1,    u: 'L/h', d: 0 },   // 0x0B3B debit instantane
    2860: { m: 10,   u: 'W',   d: 0 },   // 0x0B2C puissance (x10 W)
    3092: { m: 0.01, u: 'm\u00b3',  d: 2 },  // 0x0C14 volume cumule (x0,01)
    3093: { m: 0.1,  u: 'm\u00b3',  d: 1 },  // 0x0C15 volume cumule (x0,1 DN50+)
    3078: { m: 1,    u: 'kWh', d: 0 },   // 0x0C06 energie
    3079: { m: 10,   u: 'kWh', d: 0 }    // 0x0C07 energie (x10 DN50+)
};
function caloRow(label, val, unit, uVal) {
    var disp, udisp = '';
    var n = Number(uVal);
    if (isNaN(n)) n = parseInt(String(uVal), 16);
    var spec = n ? CALO_UNITS[n] : null;
    if (spec) {
        var v = parseFloat(val);
        disp = isBad(v) ? '--' : (v * spec.m).toFixed(spec.d);
        udisp = spec.u;
    } else {
        disp = fv(val, unit || '', 1);
        if (n) udisp = 'u:0x' + n.toString(16).toUpperCase();
    }
    return '<tr><td class="calo-label">' + label + '</td>' +
           '<td class="calo-value">' + disp + '</td>' +
           '<td class="calo-unit">' + udisp + '</td></tr>';
}
html += '<div class="calo-block">';
html += '<div class="calo-title">Calorimètre chauffage</div>';
html += '<table class="calo-table"><tbody>';
html += caloRow('Puissance', e['heat_calo_pwr'], '', e['heat_calo_pwrU']);
html += caloRow('Énergie chauffage', e['heat_calo_hKwh'], '', e['heat_calo_hKwhU']);
html += caloRow('Énergie refroidissement', e['heat_calo_cKwh'], '', e['heat_calo_cKwhU']);
html += caloRow('Débit', e['heat_calo_qe'], '', e['heat_calo_qeU']);
html += caloRow('Volume total', e['heat_calo_qeTot'], '', e['heat_calo_qeTotU']);
html += caloRow('T° aller', e['heat_calo_tIn'], ' °C');
html += caloRow('T° retour', e['heat_calo_tRet'], ' °C');
html += '</tbody></table></div>';

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
// banner TB : nom du state deja correct ('Départ chauffage')

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

return html;