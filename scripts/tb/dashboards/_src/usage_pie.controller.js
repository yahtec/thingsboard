// scripts/tb/widgets/refactor/usage_pie/controller.js
//
// Widget Usage Pie refactored to read pac_v2 json_v.
// Lit la pac_v2 a 2 bornes (start, end) et calcule delta des compteurs firmware
// HPs[i].HP.time + HPs[i].boil.time.
//
// CHANGEMENT FONCTIONNEL : le 4e slice "PAC + gaz" (hybride) est SUPPRIME.
// Le calcul d'overlap demandait de scanner les statuses sur toute la fenetre
// (~500k points). Avec pac_v2 (1 row JSON par sample, ~2.6 KB), reconstruire
// l'overlap couterait ~112 MB de transfert pour 30 jours.
// Le widget passe a 3 slices : PAC seule + Chaudiere seule + Arret. Si overlap
// reactive un jour, agreger statuses cote serveur (rule node ou attribut SHARED).
//
// La detection unite (seconds vs hours) reste utile pour periodes anciennes ou
// les compteurs etaient en heures avant le firmware 2026-04.

var COLORS = {
    pac:    '#1976d2',
    boil:   '#e53935',
    off:    '#bdbdbd'
};
var LABELS = {
    pac:    'PAC seule',
    boil:   'Chaudière seule',
    off:    'Arrêt'
};
var SLICE_ORDER = ['pac', 'boil', 'off'];

var PRESETS = [
    { id: '24h', label: '24 h',   ms: 86400 * 1000 },
    { id: '7j',  label: '7 j',    ms: 7  * 86400 * 1000 },
    { id: '30j', label: '30 j',   ms: 30 * 86400 * 1000 },
    { id: '90j', label: '90 j',   ms: 90 * 86400 * 1000 },
    { id: '12m', label: '12 mois', ms: 365 * 86400 * 1000 }
];
var LS_KEY = 'tduo.usagePie.range';

function resolveHpIndex(ctx) {
    try {
        if (ctx.stateController) {
            var sp = ctx.stateController.getStateParams();
            if (sp && sp.hpIndex) return Number(sp.hpIndex);
        }
    } catch(_){}
    if (ctx.settings && ctx.settings.hpIndex) return Number(ctx.settings.hpIndex);
    return null;
}

self.onInit = function() {
    var ctx = self.ctx;
    ctx.$container.addClass('usage-pie-host');

    // Mode retroview : on cache (compteurs cumules incompatibles avec rejouage).
    try {
        var __rv = sessionStorage.getItem('tduo.retroview.endTs');
        if (__rv) {
            ctx.$container.html(
                '<div class="upie-retroview-blocked">' +
                  '<div class="upie-retroview-icon">🕒</div>' +
                  '<div class="upie-retroview-msg">Camembert indisponible en mode rétroview.</div>' +
                  '<div class="upie-retroview-sub">Quittez la rétroview pour voir la répartition d\'utilisation.</div>' +
                '</div>'
            );
            return;
        }
    } catch(_e) {}

    self._renderWidget();

    // Filtre admin/customer (logique d'origine conservee).
    function _candidateCells() {
        var arr = [];
        var el = ctx.$container[0];
        for (var i = 0; i < 12 && el && el !== document.body; i++, el = el.parentElement) {
            var tag = (el.tagName || '').toLowerCase();
            var cls = el.classList && el.classList.value || '';
            if (tag === 'gridster-item' || tag === 'tb-widget' || tag === 'tb-widget-container'
                || /gridster-item|tb-widget|widget-container/.test(cls)) {
                arr.push(el);
            }
        }
        return arr;
    }
    function _hideAll() {
        _candidateCells().forEach(function(c){ c.style.setProperty('display', 'none', 'important'); });
        ctx.$container[0].style.setProperty('display', 'none', 'important');
    }
    var tok = localStorage.getItem('jwt_token');
    if (!tok) return;
    var H = { 'X-Authorization': 'Bearer ' + tok };
    fetch('/api/auth/user', { headers: H })
        .then(function(r){ return r.ok ? r.json() : null; })
        .then(function(me){
            if (!me) { _hideAll(); return; }
            if (me.authority === 'TENANT_ADMIN') return;
            if (me.authority !== 'CUSTOMER_USER') { _hideAll(); return; }
            return fetch('/api/plugins/telemetry/USER/' + me.id.id + '/values/attributes/SERVER_SCOPE?keys=is_admin', { headers: H })
                .then(function(r){ return r.ok ? r.json() : []; })
                .then(function(attrs){
                    var ok = (attrs || []).some(function(a){ return a.key === 'is_admin' && a.value === true; });
                    if (!ok) _hideAll();
                });
        }).catch(function(){ _hideAll(); });
};

self._renderWidget = function() {
    var ctx = self.ctx;
    var presetsHtml = PRESETS.map(function(p) {
        return '<button type="button" class="upie-preset" data-preset="' + p.id + '">' + p.label + '</button>';
    }).join('') + '<button type="button" class="upie-preset" data-preset="custom">Personnalisé</button>';
    var hp = resolveHpIndex(ctx);
    var title = hp ? ('Utilisation PAC ' + hp) : "Répartition d'utilisation";
    ctx.$container.html(
        '<div class="upie-head">' +
          '<span class="upie-title">' + title + '</span>' +
          '<span class="upie-period" id="upie-period">—</span>' +
        '</div>' +
        '<div class="upie-presets" id="upie-presets">' + presetsHtml + '</div>' +
        '<div class="upie-custom" id="upie-custom">' +
          '<label>Du</label><input type="date" id="upie-from">' +
          '<label>au</label><input type="date" id="upie-to">' +
          '<button type="button" id="upie-apply">Appliquer</button>' +
        '</div>' +
        '<div class="upie-body" id="upie-body">' +
          '<div class="upie-loading">Chargement…</div>' +
        '</div>' +
        '<div class="upie-foot" id="upie-foot">PAC/Chaud = compteurs firmware (pac_v2.HPs[i].HP.time + .boil.time).</div>'
    );

    self._range = self._loadRange();
    self._wirePresets();
    self._applyPresetButtons();
    self._refresh();
};

self._loadRange = function() {
    try {
        var raw = localStorage.getItem(LS_KEY);
        if (raw) {
            var p = JSON.parse(raw);
            if (p && p.preset === 'custom' && p.start && p.end) {
                return { preset: 'custom', start: p.start, end: p.end };
            }
            if (p && p.preset) {
                var preset = PRESETS.filter(function(x){ return x.id === p.preset; })[0];
                if (preset) {
                    var end = Date.now();
                    return { preset: p.preset, start: end - preset.ms, end: end };
                }
            }
        }
    } catch(_) {}
    var end = Date.now();
    var defP = PRESETS.filter(function(x){ return x.id === '30j'; })[0];
    return { preset: '30j', start: end - defP.ms, end: end };
};

self._saveRange = function() {
    try {
        var r = self._range;
        var p = { preset: r.preset };
        if (r.preset === 'custom') { p.start = r.start; p.end = r.end; }
        localStorage.setItem(LS_KEY, JSON.stringify(p));
    } catch(_) {}
};

self._wirePresets = function() {
    var root = self.ctx.$container[0];
    root.querySelectorAll('[data-preset]').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var id = btn.getAttribute('data-preset');
            if (id === 'custom') {
                var pane = document.getElementById('upie-custom');
                var open = pane.classList.toggle('open');
                if (open) {
                    document.getElementById('upie-from').value = ymd(self._range.start);
                    document.getElementById('upie-to').value   = ymd(self._range.end);
                }
                return;
            }
            var preset = PRESETS.filter(function(x){ return x.id === id; })[0];
            if (!preset) return;
            var end = Date.now();
            self._range = { preset: id, start: end - preset.ms, end: end };
            self._saveRange();
            document.getElementById('upie-custom').classList.remove('open');
            self._applyPresetButtons();
            self._refresh();
        });
    });
    var apply = root.querySelector('#upie-apply');
    if (apply) apply.addEventListener('click', function() {
        var fromV = document.getElementById('upie-from').value;
        var toV   = document.getElementById('upie-to').value;
        if (!fromV || !toV) return;
        var s = new Date(fromV + 'T00:00:00').getTime();
        var e = new Date(toV   + 'T23:59:59').getTime();
        if (!(s < e)) return;
        self._range = { preset: 'custom', start: s, end: e };
        self._saveRange();
        self._applyPresetButtons();
        self._refresh();
    });
};

self._applyPresetButtons = function() {
    var root = self.ctx.$container[0];
    root.querySelectorAll('[data-preset]').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-preset') === self._range.preset);
    });
};

function ymd(ts) {
    var d = new Date(ts);
    var p = function(n){ return n < 10 ? '0'+n : n; };
    return d.getFullYear() + '-' + p(d.getMonth()+1) + '-' + p(d.getDate());
}

self.onDataUpdated = function() {};
self.onUpdateTimewindow = function() {};
self.onLatestDataUpdated = function() {};
self.onResize = function() {};
self.onDestroy = function() {};

self._refresh = function() {
    var ctx = self.ctx;
    var body = document.getElementById('upie-body');
    if (!body) return;
    body.innerHTML = '<div class="upie-loading">Chargement…</div>';

    var ds = (ctx.datasources && ctx.datasources[0]) || null;
    var devId = ds && (ds.entityId || (ds.entity && ds.entity.id && ds.entity.id.id));
    if (!devId) {
        body.innerHTML = '<div class="upie-empty">Aucune chaufferie sélectionnée.</div>';
        return;
    }
    var r = self._range || { start: Date.now() - 30*86400*1000, end: Date.now() };
    if (r.preset && r.preset !== 'custom') {
        var p = PRESETS.filter(function(x){ return x.id === r.preset; })[0];
        if (p) { r.end = Date.now(); r.start = r.end - p.ms; }
    }
    var start = r.start, end = r.end;
    document.getElementById('upie-period').textContent = fmtPeriod(start, end);

    var hpIndex = resolveHpIndex(ctx);
    var tok = localStorage.getItem('jwt_token');
    var headers = { 'X-Authorization': 'Bearer ' + tok };

    // 1 fetch latest pac_v2 avant start (compteur de depart)
    // 1 fetch latest pac_v2 avant end   (compteur de fin)
    // Fallback : premier pac_v2 dans la fenetre.
    var preUrl = '/api/plugins/telemetry/DEVICE/' + devId +
        '/values/timeseries?keys=pac_v2&startTs=0&endTs=' + start +
        '&limit=1&orderBy=DESC&agg=NONE';
    var firstInWinUrl = '/api/plugins/telemetry/DEVICE/' + devId +
        '/values/timeseries?keys=pac_v2&startTs=' + start + '&endTs=' + end +
        '&limit=1&orderBy=ASC&agg=NONE';
    var endUrl = '/api/plugins/telemetry/DEVICE/' + devId +
        '/values/timeseries?keys=pac_v2&startTs=0&endTs=' + end +
        '&limit=1&orderBy=DESC&agg=NONE';

    Promise.all([
        fetch(preUrl,        { headers: headers }).then(function(r){ return r.ok ? r.json() : {}; }),
        fetch(firstInWinUrl, { headers: headers }).then(function(r){ return r.ok ? r.json() : {}; }),
        fetch(endUrl,        { headers: headers }).then(function(r){ return r.ok ? r.json() : {}; })
    ]).then(function(res) {
        var prePoint = pickPoint(res[0]) || pickPoint(res[1]);
        var endPoint = pickPoint(res[2]);
        if (!prePoint || !endPoint) {
            body.innerHTML = '<div class="upie-empty">Pas de données pac_v2 sur la période.</div>';
            return;
        }
        var preP = parsePacV2(prePoint.value);
        var endP = parsePacV2(endPoint.value);
        if (!preP || !endP) {
            body.innerHTML = '<div class="upie-empty">Données pac_v2 invalides.</div>';
            return;
        }

        var wallclockMs = end - start;
        var hpRange = hpIndex ? [hpIndex] : [1, 2, 3, 4];
        var mode = detectMode(preP, endP, wallclockMs, hpRange);

        var totalPacMs = 0, totalBoilMs = 0;
        var activeHPs = [];
        hpRange.forEach(function(i) {
            var preHp = (preP.HPs || [])[i - 1] || {};
            var endHp = (endP.HPs || [])[i - 1] || {};
            var commActive = (preHp.comm === true) || (endHp.comm === true);
            if (!commActive) return;
            activeHPs.push(i);
            var pacDelta = counterToMs((preHp.HP || {}).time, (endHp.HP || {}).time, wallclockMs, mode);
            var boilDelta = counterToMs((preHp.boil || {}).time, (endHp.boil || {}).time, wallclockMs, mode);
            if (pacDelta !== null)  totalPacMs  += pacDelta;
            if (boilDelta !== null) totalBoilMs += boilDelta;
        });
        totalPacMs  = Math.min(totalPacMs,  wallclockMs);
        totalBoilMs = Math.min(totalBoilMs, wallclockMs);

        // 3 slices : pac, boil, off. Pas d'overlap (cf. doc en-tete).
        // Pour eviter pac + boil > wallclock (concurrence theorique), on ramene
        // proportionnellement si necessaire.
        var sumActive = totalPacMs + totalBoilMs;
        if (sumActive > wallclockMs && sumActive > 0) {
            var ratio = wallclockMs / sumActive;
            totalPacMs = totalPacMs * ratio;
            totalBoilMs = totalBoilMs * ratio;
        }
        var off = Math.max(0, wallclockMs - totalPacMs - totalBoilMs);
        render(body, { pac: totalPacMs, boil: totalBoilMs, off: off }, {
            wallclockMs: wallclockMs, unitDetected: mode,
            hpIndex: hpIndex, activeHPs: activeHPs
        });
    }).catch(function(err) {
        body.innerHTML = '<div class="upie-empty">Erreur: ' + (err && err.message ? err.message : err) + '</div>';
    });
};

function pickPoint(resp) {
    if (!resp || !resp.pac_v2 || !resp.pac_v2.length) return null;
    return resp.pac_v2[0];
}

function parsePacV2(raw) {
    if (raw === null || raw === undefined) return null;
    try { return (typeof raw === 'string') ? JSON.parse(raw) : raw; }
    catch (e) { return null; }
}

function detectMode(preP, endP, wallclockMs, hpRange) {
    var wallSec = wallclockMs / 1000;
    var tol = 1.05;
    var sawSwitch = false;
    hpRange.forEach(function(i) {
        var preHp = (preP.HPs || [])[i - 1] || {};
        var endHp = (endP.HPs || [])[i - 1] || {};
        var pairs = [
            [ (preHp.HP || {}).time,   (endHp.HP || {}).time ],
            [ (preHp.boil || {}).time, (endHp.boil || {}).time ]
        ];
        pairs.forEach(function(p) {
            var s = numOrNull(p[0]), e = numOrNull(p[1]);
            if (s === null || e === null || e < s) return;
            var d = e - s;
            if (d === 0) return;
            var canSec = d <= wallSec * tol;
            var canHr  = d * 3600 <= wallSec * tol;
            if (!canSec && !canHr) {
                var dSw = e - s * 3600;
                if (dSw >= 0 && dSw <= wallSec * tol) sawSwitch = true;
            }
        });
    });
    return sawSwitch ? 'switch' : 'seconds';
}

function counterToMs(startV, endV, wallclockMs, mode) {
    var s = numOrNull(startV), e = numOrNull(endV);
    if (s === null || e === null) return null;
    if (e < s) return null;
    var d = e - s;
    if (d === 0) return 0;
    var wallSec = wallclockMs / 1000;
    if (mode === 'switch') {
        var dSw = e - s * 3600;
        if (dSw < 0) dSw = 0;
        return Math.min(dSw * 1000, wallclockMs);
    }
    if (mode === 'hours') return Math.min(d * 3600 * 1000, wallclockMs);
    // default seconds
    return Math.min(d * 1000, wallclockMs);
}

function numOrNull(v) {
    if (v === null || v === undefined || v === '') return null;
    var n = Number(v);
    return isFinite(n) ? n : null;
}

function render(host, buckets, meta) {
    var sum = buckets.pac + buckets.boil + buckets.off;
    var foot = document.getElementById('upie-foot');
    if (sum <= 0) {
        host.innerHTML = '<div class="upie-empty">Aucune donnée sur la période.</div>';
        return;
    }
    var svg = renderSvg(buckets, sum);
    var legend = renderLegend(buckets, sum);
    host.innerHTML = '';
    host.appendChild(svg);
    host.appendChild(legend);
    if (foot) {
        var u = meta.unitDetected;
        var unitTxt = u === 'hours' ? 'h' : u === 'seconds' ? 's' : u === 'switch' ? 'bascule h→s' : '?';
        var scope = meta.hpIndex ? ('HP' + meta.hpIndex)
                                 : (meta.activeHPs && meta.activeHPs.length ? ('HP' + meta.activeHPs.join('+')) : '—');
        foot.textContent =
            'PAC/Chaud = compteurs pac_v2 (unité ' + unitTxt + ') · périmètre : ' + scope + '.';
    }
}

function renderSvg(buckets, sum) {
    var size = 180, cx = size/2, cy = size/2, r = 70, inner = 42;
    var ns = 'http://www.w3.org/2000/svg';
    var wrap = document.createElement('div');
    wrap.className = 'upie-svg-wrap';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'upie-svg');
    svg.setAttribute('width', size); svg.setAttribute('height', size);
    svg.setAttribute('viewBox', '0 0 ' + size + ' ' + size);

    var bg = document.createElementNS(ns, 'circle');
    bg.setAttribute('class', 'bg');
    bg.setAttribute('cx', cx); bg.setAttribute('cy', cy); bg.setAttribute('r', r);
    svg.appendChild(bg);

    var nonZero = SLICE_ORDER.filter(function(k){ return buckets[k] > 0; });
    if (nonZero.length === 1) {
        var only = document.createElementNS(ns, 'circle');
        only.setAttribute('cx', cx); only.setAttribute('cy', cy); only.setAttribute('r', r);
        only.setAttribute('fill', COLORS[nonZero[0]]);
        svg.appendChild(only);
    } else {
        var start = -Math.PI / 2;
        SLICE_ORDER.forEach(function(k) {
            var v = buckets[k];
            if (v <= 0) return;
            var angle = (v / sum) * Math.PI * 2;
            var endA = start + angle;
            var path = arcPath(cx, cy, r, start, endA);
            var p = document.createElementNS(ns, 'path');
            p.setAttribute('d', path);
            p.setAttribute('fill', COLORS[k]);
            svg.appendChild(p);
            start = endA;
        });
    }

    var hole = document.createElementNS(ns, 'circle');
    hole.setAttribute('cx', cx); hole.setAttribute('cy', cy); hole.setAttribute('r', inner);
    hole.setAttribute('fill', '#fff');
    svg.appendChild(hole);

    var activeMs = buckets.pac + buckets.boil;
    var pctActive = Math.round(100 * activeMs / sum);
    var t1 = document.createElementNS(ns, 'text');
    t1.setAttribute('class', 'total-val upie-text-center');
    t1.setAttribute('x', cx); t1.setAttribute('y', cy - 6);
    t1.textContent = pctActive + '%';
    svg.appendChild(t1);
    var t2 = document.createElementNS(ns, 'text');
    t2.setAttribute('class', 'total-lbl upie-text-center');
    t2.setAttribute('x', cx); t2.setAttribute('y', cy + 11);
    t2.textContent = 'temps actif';
    svg.appendChild(t2);

    wrap.appendChild(svg);
    return wrap;
}

function arcPath(cx, cy, r, start, end) {
    var x1 = cx + r * Math.cos(start), y1 = cy + r * Math.sin(start);
    var x2 = cx + r * Math.cos(end),   y2 = cy + r * Math.sin(end);
    var large = (end - start) > Math.PI ? 1 : 0;
    return 'M ' + cx + ' ' + cy +
           ' L ' + x1 + ' ' + y1 +
           ' A ' + r + ' ' + r + ' 0 ' + large + ' 1 ' + x2 + ' ' + y2 + ' Z';
}

function renderLegend(buckets, sum) {
    var wrap = document.createElement('div');
    wrap.className = 'upie-legend';
    SLICE_ORDER.forEach(function(k) {
        var ms = buckets[k];
        var pct = sum > 0 ? (100 * ms / sum) : 0;
        var row = document.createElement('div');
        row.className = 'upie-row';
        row.innerHTML =
            '<span class="upie-swatch" style="background:' + COLORS[k] + '"></span>' +
            '<span class="upie-lbl">' + LABELS[k] + '</span>' +
            '<span class="upie-pct">' + (pct < 0.05 ? '0' : pct.toFixed(1)) + '%</span>' +
            '<span class="upie-dur">' + fmtDuration(ms) + '</span>';
        wrap.appendChild(row);
    });
    return wrap;
}

function fmtDuration(ms) {
    if (ms <= 0) return '—';
    var s = Math.floor(ms / 1000);
    var d = Math.floor(s / 86400); s -= d * 86400;
    var h = Math.floor(s / 3600); s -= h * 3600;
    var m = Math.floor(s / 60);
    if (d > 0) return d + 'j ' + h + 'h';
    if (h > 0) return h + 'h ' + m + 'min';
    if (m > 0) return m + ' min';
    return Math.max(1, Math.floor(ms/1000)) + ' s';
}

function fmtPeriod(start, end) {
    function f(ts, withTime) {
        var d = new Date(ts);
        var pad = function(n){ return n < 10 ? '0'+n : n; };
        var s = pad(d.getDate()) + '/' + pad(d.getMonth()+1) + '/' + d.getFullYear();
        if (withTime) s += ' ' + pad(d.getHours()) + 'h';
        return s;
    }
    var span = end - start;
    var withTime = span <= 7 * 86400 * 1000;
    return f(start, withTime) + ' → ' + f(end, withTime);
}
