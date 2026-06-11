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
function buildValueRow(label, value, unit, decimals) {
    return '<div class="val-row"><span class="val-label">'+label+'</span><span class="val-value">'+fv(value,unit,decimals)+'</span></div>';
}

var html = '<div class="pac-detail-frame boiler-frame">';
html += '<div class="frame-header"><h2 class="frame-title boiler-title">Données Chaudière '+idx+'</h2></div>';
html += '<div class="boiler-row">';
html += '<div class="values-block"><div class="sub-title">Chaudière</div>';
html += buildValueRow('T° entrée',e[prefix+'tOut'],'°C',1);
html += buildValueRow('T° sortie',e[prefix+'boil_tOut'],'°C',1);
html += buildValueRow('T° fumée',e[prefix+'boil_tSmoke'],'°C',1);
html += buildValueRow('Débit eau',e[prefix+'boil_qe'],' L/h',0);
html += buildValueRow('Vitesse brûleur',e[prefix+'boil_rpm'],' rpm',0);
/* TBN-TIME-UNIT-BEGIN */
var __tUnit = 'seconds';
function tH(v) {
  if (v === null || v === undefined || v === '') return v;
  var n = Number(v);
  if (!isFinite(n)) return v;
  return __tUnit === 'seconds' ? (n / 3600) : n;
}
/* TBN-TIME-UNIT-END */
html += buildValueRow('Temps de fonctionnement',tH(e[prefix+'boil_time']),' h',0);
html += '</div>';
html += '<div class="values-block"><div class="sub-title">Pompe</div>';
html += buildValueRow('Vitesse',e[prefix+'pump_rpm'],' rpm',0);
html += buildValueRow('DeltaP',e[prefix+'pump_dP'],' mCE',2);
html += buildValueRow('Puissance',e[prefix+'pump_pwr'],' W',0);
html += buildValueRow('Débit',e[prefix+'pump_qe'],' L/h',0);
html += buildValueRow('Durée ON',tH(e[prefix+'pump_time']),' h',0);
html += '</div>';
html += '</div>';
html += '</div>';

return html;
