var ctxRef = (typeof ctx !== 'undefined' && ctx) ? ctx : (typeof self !== 'undefined' ? self.ctx : null);
var sp = (ctxRef && ctxRef.stateController) ? (ctxRef.stateController.getStateParams() || {}) : {};
var idx = sp.hpIndex || sp.hp || 1;
var prefix = 'HP' + idx + '_';

var html = '<div class="chart-frame">';
html += '<div class="chart-title-bar"><span class="chart-title">Courbes PAC (24 heures)</span></div>';
html += '<div class="chart-container" style="position:relative">';
html += '<svg id="chart-svg-pac" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%;display:block"></svg>';
html += '<div id="chart-tooltip-pac" style="display:none;position:absolute;background:rgba(0,0,0,0.75);color:#fff;padding:8px 12px;border-radius:6px;font-size:12px;pointer-events:none;z-index:10;line-height:1.6"></div>';
html += '</div>';
html += '<div id="chart-legend-pac" class="chart-legend"></div>';
html += '</div>';

var _prefix = prefix;
// Preserve visByPrefix entre les re-renders (sinon le toggle legend est reset a chaque tick)
var _prevChart = window.__tbChartPac || {};
if (_prevChart.interval) clearInterval(_prevChart.interval);
if (_prevChart.poller)   clearInterval(_prevChart.poller);
if (_prevChart.listener) document.removeEventListener('mousemove', _prevChart.listener);
if (_prevChart.sub && typeof _prevChart.sub.unsubscribe === 'function') {
    try { _prevChart.sub.unsubscribe(); } catch(e) {}
}
if (_prevChart.ro) { try { _prevChart.ro.disconnect(); } catch(e) {} }
window.__tbChartPac = { visByPrefix: _prevChart.visByPrefix || {} };

setTimeout(function() {
    var DEVICE_ID = (function(){
        try {
            var ds = ctxRef && ctxRef.datasources && ctxRef.datasources[0];
            if (ds && ds.entityId) return ds.entityId;
            if (ds && ds.entity && ds.entity.id) return ds.entity.id.id;
        } catch (e) {}
        return null;  // alias resolution failed — fetchSeries will bail
    })();

    // === Timeline custom: lit window depuis sessionStorage. Cle 'tduo.retroview.spanH'
    // (heures) + 'tduo.retroview.endTs' (ms epoch). Absence => spanH=24, endTs=now. ===
    var TDUO_TIMELINE = {
        getSpanH: function() {
            var v = parseInt(sessionStorage.getItem('tduo.retroview.spanH') || '24', 10);
            return (isNaN(v) || v <= 0) ? 24 : v;
        },
        getEndTs: function() {
            var v = sessionStorage.getItem('tduo.retroview.endTs');
            if (v) { var t = parseInt(v, 10); if (t > 0) return t; }
            return Date.now();
        },
        isLive: function() { return !sessionStorage.getItem('tduo.retroview.endTs'); }
    };
    var showAxes = false; // cache graduations Y (degC / Hz / kW / pas)
    var REFRESH_MS = 30000;
    var lastDrawnWindow = null;

    // Chaque série pointe vers un "axis" (left/freq/pwr). freq+pwr sont dessinés côté droit
    // avec leur propre échelle; les graduations affichent Hz (intérieur) et kW (extérieur).
    var SERIES = [
        { key: _prefix+'tIn',         label: 'T° entrée PAC',      color: '#42a5f5', axis: 'left', unit: '°C' },
        { key: _prefix+'tOut',        label: 'T° sortie PAC',      color: '#ef5350', axis: 'left', unit: '°C' },
        { key: _prefix+'tCond',       label: 'T° condensation',    color: '#ff7043', axis: 'left', unit: '°C' },
        { key: _prefix+'tEvap',       label: 'T° évaporation',     color: '#26c6da', axis: 'left', unit: '°C' },
        { key: 'tExt',                label: 'T° extérieure',      color: '#90a4ae', axis: 'left', unit: '°C' },
        { key: _prefix+'tSC',         label: 'Sous-refroidissement', color: '#8d6e63', axis: 'left', unit: '°C' },
        { key: _prefix+'tOH',         label: 'Surchauffe',         color: '#fbc02d', axis: 'left', unit: '°C' },
        { key: _prefix+'invert_freq', label: 'Fréq compresseur',   color: '#66bb6a', axis: 'freq', unit: ' Hz' },
        { key: _prefix+'invert_pwr',  label: 'Puiss compresseur',  color: '#ab47bc', axis: 'pwr',  unit: ' W' },
        { key: _prefix+'dpf',         label: 'Position détendeur', color: '#5c6bc0', axis: 'dpf',  unit: ' pas' }
    ];
    // Plages Y fixes (plage d'exploitation normale de l'installation)
    var AXIS = {
        left: { min: -30, max: 90,    decimals: 0, side: 'left',  color: '#555', fmt: function(v){ return v.toFixed(0); } },
        freq: { min: 0,   max: 120,   decimals: 0, side: 'right', color: '#66bb6a', fmt: function(v){ return v.toFixed(0); } },
        pwr:  { min: 0,   max: 30000, decimals: 0, side: 'right', color: '#ab47bc', fmt: function(v){ return (v/1000).toFixed(0); } },
        dpf:  { min: 0,   max: 2200,  decimals: 0, side: 'right', color: '#5c6bc0', fmt: function(v){ return v.toFixed(0); } }
    };
    // Seuil -50 pour ne pas laisser passer les agrégats AVG des sondes débranchées
    // (sentinelle -99.9 lissée peut ressortir vers -95..-70 selon la fenêtre d'agrégation).
    // Aucune sonde HVAC réelle ne descend sous -50°C en exploitation.
    function isBad(v) {
        // Sentinelles firmware: -99.9 (sonde déconnectée) ET -47.8
        // (code de défaut). Aucune sonde HVAC réelle ne descend sous -45 °C.
        return v == null || isNaN(v) || v <= -45;
    }

    var seriesData = {};
    // visibility scope par prefix (HP1_, HP2_...) pour independance entre PACs
    window.__tbChartPac.visByPrefix[_prefix] = window.__tbChartPac.visByPrefix[_prefix] || {};
    var visibility = window.__tbChartPac.visByPrefix[_prefix];
    SERIES.forEach(function(s) { if (!(s.key in visibility)) visibility[s.key] = true; });

    function getToken() { return localStorage.getItem('jwt_token'); }

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
        // aim for ~300 points
        var iv = Math.max(1000, Math.round(span / 300));
        // round up to common steps
        var steps = [1000, 5000, 10000, 30000, 60000, 300000, 600000, 900000, 1800000, 3600000, 7200000, 14400000, 86400000];
        for (var i = 0; i < steps.length; i++) {
            if (iv <= steps[i]) return steps[i];
        }
        return 86400000;
    }

    function fetchSeries() {
        if (!DEVICE_ID) { console.warn('[chart] no entityId resolved — skipping fetch'); return; }
        var w = getTimeWindow();
        lastDrawnWindow = w;
        var iv = getAggInterval(w);
        var keys = SERIES.map(function(s) { return s.key; }).join(',');
        var url = '/api/plugins/telemetry/DEVICE/' + DEVICE_ID +
            '/values/timeseries?keys=' + keys +
            '&startTs=' + w.startTs + '&endTs=' + w.endTs +
            '&interval=' + iv + '&agg=NONE&limit=20000';
        fetch(url, { headers: { 'X-Authorization': 'Bearer ' + getToken() } })
            .then(function(r) { return r.json(); })
            .then(function(d) {
                seriesData = d;
                var dateEl = document.getElementById('frame-date-val');
                if (dateEl) {
                    var latestTs = 0;
                    SERIES.forEach(function(s) {
                        (seriesData[s.key] || []).forEach(function(p) {
                            var ts = parseInt(p.ts, 10);
                            if (ts > latestTs) latestTs = ts;
                        });
                    });
                    if (latestTs > 0) {
                        var dd = new Date(latestTs);
                        var pad = function(n) { return n < 10 ? '0'+n : n; };
                        dateEl.textContent = pad(dd.getDate())+'/'+pad(dd.getMonth()+1)+'/'+dd.getFullYear()+' '+pad(dd.getHours())+':'+pad(dd.getMinutes());
                    }
                }
                drawChart();
                drawLegend();
            })
            .catch(function(err) { console.warn('pac chart fetch error', err); });
    }

    function drawChart() {
        var svg = document.getElementById('chart-svg-pac');
        if (!svg) return;
    // Monotone-cubic-Hermite path (Fritsch-Carlson). No overshoot at extrema.
    function smoothPath(pts) {
        var n = pts.length;
        if (n === 0) return '';
        if (n === 1) return 'M' + pts[0].x.toFixed(1) + ',' + pts[0].y.toFixed(1);
        if (n === 2) return 'M' + pts[0].x.toFixed(1) + ',' + pts[0].y.toFixed(1)
                          + 'L' + pts[1].x.toFixed(1) + ',' + pts[1].y.toFixed(1);
        var m = new Array(n - 1); // slope of secant i..i+1
        for (var i = 0; i < n - 1; i++) {
            var dx = pts[i+1].x - pts[i].x;
            m[i] = dx === 0 ? 0 : (pts[i+1].y - pts[i].y) / dx;
        }
        var t = new Array(n); // tangent at each point
        t[0] = m[0];
        t[n-1] = m[n-2];
        for (var i = 1; i < n - 1; i++) {
            if (m[i-1] * m[i] <= 0) {
                t[i] = 0;
            } else {
                t[i] = (m[i-1] + m[i]) / 2;
                // Fritsch-Carlson monotonicity guard
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


        // Échelle pwr dynamique : si la mesure dépasse la pleine échelle (30 kW),
        // on remonte AXIS.pwr.max au multiple de 5 kW supérieur pour ne pas écrêter la courbe.
        var _pwrKey = _prefix+'invert_pwr';
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
        var hasDpf  = SERIES.some(function(s){ return s.axis==='dpf'  && visibility[s.key]; });
        var narrow = w < 600;
        // On mobile, one seule colonne d'étiquettes à droite pour économiser la largeur.
        // La colonne interne (pwr) est masquée; tooltip conserve la valeur en W.
        // kW affiché aussi sur mobile (colonnes plus serrées)
        var showPwrLabels = hasPwr;
        var padL = showAxes ? 40 : 12;
        var padR = 12;
        var kwOffset = narrow ? 26 : 33; // gap horizontal Hz → kW
        var dpfOffset = narrow ? 52 : 66; // gap Hz to pas (after kW)
        if (showAxes && hasFreq)      padR += narrow ? 24 : 28;
        if (showAxes && showPwrLabels) padR += narrow ? 26 : 30;
        if (showAxes && hasDpf)        padR += narrow ? 26 : 30;
        var padT = 20, padB = narrow ? 46 : 32;
        var iw = w - padL - padR, ih = h - padT - padB;
        var tw = lastDrawnWindow || getTimeWindow();
        function xOf(ts) { return padL + ((ts - tw.startTs) / (tw.endTs - tw.startTs)) * iw; }
        function yOf(axisId, v) {
            var a = AXIS[axisId];
            return padT + ih - ((v - a.min) / (a.max - a.min)) * ih;
        }
        var sc = '';
        // Graduations verticales + étiquettes multi-échelles
        // yTicks ∈ {3, 4, 6} — choisis pour que les 3 échelles aient toutes un step rond :
        //   - 6 : °C step=20, Hz step=20, kW step=5
        //   - 4 : °C step=30, Hz step=30, kW step=7.5 (accepté)
        //   - 3 : °C step=40, Hz step=40, kW step=10
        var yTicks = ih >= 260 ? 6 : (ih >= 160 ? 4 : 3);
        for (var i = 0; i <= yTicks; i++) {
            var t = i / yTicks; // 0 en haut .. 1 en bas
            var y = padT + t * ih;
            sc += '<line x1="'+padL+'" y1="'+y+'" x2="'+(padL+iw)+'" y2="'+y+'" stroke="#eee" stroke-width="1"/>';
            // Étiquette gauche : °C
            var vL = AXIS.left.max - t * (AXIS.left.max - AXIS.left.min);
            if (showAxes) sc += '<text x="'+(padL-6)+'" y="'+(y+4)+'" text-anchor="end" font-size="10" fill="'+AXIS.left.color+'">'+AXIS.left.fmt(vL)+'</text>';
            // Étiquette droite interne : Hz (vert)
            if (hasFreq) {
                var vF = AXIS.freq.max - t * (AXIS.freq.max - AXIS.freq.min);
                if (showAxes) sc += '<text x="'+(padL+iw+5)+'" y="'+(y+4)+'" text-anchor="start" font-size="10" fill="'+AXIS.freq.color+'">'+AXIS.freq.fmt(vF)+'</text>';
            }
            // Étiquette droite externe : kW (violet)
            if (showPwrLabels) {
                var vP = AXIS.pwr.max - t * (AXIS.pwr.max - AXIS.pwr.min);
                if (showAxes) sc += '<text x="'+(padL+iw+kwOffset)+'" y="'+(y+4)+'" text-anchor="start" font-size="10" fill="'+AXIS.pwr.color+'">'+AXIS.pwr.fmt(vP)+'</text>';
            }
            if (hasDpf) {
                var vD = AXIS.dpf.max - t * (AXIS.dpf.max - AXIS.dpf.min);
                if (showAxes) sc += '<text x="'+(padL+iw+dpfOffset)+'" y="'+(y+4)+'" text-anchor="start" font-size="10" fill="'+AXIS.dpf.color+'">'+AXIS.dpf.fmt(vD)+'</text>';
            }
        }
        // Petites unités en haut à droite (décollées de la 1re graduation pour éviter chevauchement)
        if (showAxes && hasFreq) sc += '<text x="'+(padL+iw+5)+'" y="'+(padT-8)+'" text-anchor="start" font-size="9" fill="'+AXIS.freq.color+'">Hz</text>';
        if (showAxes && showPwrLabels) sc += '<text x="'+(padL+iw+kwOffset)+'" y="'+(padT-8)+'" text-anchor="start" font-size="9" fill="'+AXIS.pwr.color+'">kW</text>';
        if (showAxes && hasDpf) sc += '<text x="'+(padL+iw+dpfOffset)+'" y="'+(padT-8)+'" text-anchor="start" font-size="9" fill="'+AXIS.dpf.color+'">pas</text>';
        // Densité X adaptative — min 4 ticks même en étroit, diviseur 70 pour plus de ticks
        // qu'avant sur mobile (avant : 2 ticks en 24h, maintenant : 4 au pas de 6h)
        var span = tw.endTs - tw.startTs;
        var targetTicks = Math.max(4, Math.min(10, Math.floor(iw / 70)));
        var roughStep = span / targetTicks;
        var steps = [300000, 600000, 900000, 1800000, 3600000, 7200000, 10800000, 14400000, 21600000, 43200000, 86400000, 2*86400000, 7*86400000, 14*86400000, 30*86400000];
        var tickStep = steps[steps.length-1];
        for (var si = 0; si < steps.length; si++) { if (steps[si] >= roughStep) { tickStep = steps[si]; break; } }
        var tickFmt = span <= 48*3600000 ? 'hm' : (span <= 14*86400000 ? 'dhm' : (span <= 180*86400000 ? 'md' : 'my'));
        var firstTick = Math.ceil(tw.startTs / tickStep) * tickStep;
        var rotate = narrow ? -40 : 0;
        for (var t = firstTick; t <= tw.endTs; t += tickStep) {
            var x = xOf(t); if (x < padL || x > padL+iw) continue;
            sc += '<line x1="'+x+'" y1="'+padT+'" x2="'+x+'" y2="'+(padT+ih)+'" stroke="#f0f0f0" stroke-width="1"/>';
            var dd = new Date(t), p2 = function(n){return n<10?'0'+n:n;};
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
        // Bordures en gris clair pour ne pas masquer les séries à valeur 0 (ligne en bas du plot)
        sc += '<line x1="'+padL+'" y1="'+padT+'" x2="'+padL+'" y2="'+(padT+ih)+'" stroke="#bbb" stroke-width="1"/>';
        sc += '<line x1="'+(padL+iw)+'" y1="'+padT+'" x2="'+(padL+iw)+'" y2="'+(padT+ih)+'" stroke="#bbb" stroke-width="1"/>';
        sc += '<line x1="'+padL+'" y1="'+(padT+ih)+'" x2="'+(padL+iw)+'" y2="'+(padT+ih)+'" stroke="#bbb" stroke-width="1"/>';
        // Tracé en step-after, la sentinelle -99 casse le tracé (segments séparés).
        // Pour les températures (axis 'left'), si toute la série est dans {0, fault}
        // on n'affiche rien — c'est une sonde non câblée d'une PAC inexistante.
        SERIES.forEach(function(s) {
            if (!visibility[s.key]) return;
            var arr = (seriesData[s.key] || []).slice().reverse();
            if (arr.length < 1) return;
            if (s.axis === 'left') {
                var anyReal = false;
                for (var _i = 0; _i < arr.length; _i++) {
                    var _v = parseFloat(arr[_i].value);
                    if (!isBad(_v) && _v !== 0) { anyReal = true; break; }
                }
                if (!anyReal) return;
            }
            // Collect valid points; split into segments where isBad
            var segments = [], current = [];
            for (var i = 0; i < arr.length; i++) {
                var p = arr[i], v = parseFloat(p.value);
                if (isBad(v)) { if (current.length) { segments.push(current); current = []; } continue; }
                current.push({ x: xOf(p.ts), y: yOf(s.axis, v) });
            }
            if (current.length) segments.push(current);
            var d = '';
            for (var si = 0; si < segments.length; si++) { d += smoothPath(segments[si]); }
            if (d) sc += '<path d="'+d+'" fill="none" stroke="'+s.color+'" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
        });
        svg.innerHTML = sc;
    }

    function drawLegend() {
        var legend = document.getElementById('chart-legend-pac'); if (!legend) return;
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
        var svg = document.getElementById('chart-svg-pac');
        var tip = document.getElementById('chart-tooltip-pac');
        if (!svg || !tip) return;
        var rect = svg.getBoundingClientRect();
        if (evt.clientX < rect.left || evt.clientX > rect.right || evt.clientY < rect.top || evt.clientY > rect.bottom) { tip.style.display='none'; return; }
        var hasFreq = SERIES.some(function(s){ return s.axis==='freq' && visibility[s.key]; });
        var hasPwr  = SERIES.some(function(s){ return s.axis==='pwr'  && visibility[s.key]; });
        var narrow = rect.width < 600;
        var showPwrLabels = hasPwr;
        var padL = showAxes ? 40 : 12, padR = 12;
        if (showAxes && hasFreq)      padR += narrow ? 24 : 28;
        if (showAxes && showPwrLabels) padR += narrow ? 26 : 30;
        if (showAxes && hasDpf)        padR += narrow ? 26 : 30;
        if (evt.clientX-rect.left < padL || evt.clientX-rect.left > rect.width-padR) { tip.style.display='none'; return; }
        var tw = lastDrawnWindow || getTimeWindow();
        var innerW = rect.width - padL - padR;
        var ts = tw.startTs + ((evt.clientX-rect.left-padL)/innerW)*(tw.endTs-tw.startTs);
        var lines = [];
        SERIES.forEach(function(s) {
            if (!visibility[s.key]) return;
            var arr = (seriesData[s.key] || []).filter(function(p) { return !isBad(parseFloat(p.value)); });
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
        if (!lines.length) { tip.style.display='none'; return; }  // aucune serie visible
        var dd=new Date(ts), pad=function(n){return n<10?'0'+n:n;};
        tip.innerHTML = '<div style="font-weight:bold;margin-bottom:4px">'+pad(dd.getDate())+'/'+pad(dd.getMonth()+1)+' '+pad(dd.getHours())+':'+pad(dd.getMinutes())+'</div>'+lines.join('<br>');
        tip.style.display='block';
        // Mesure réelle pour décider du flip ; offset 10 px du curseur.
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

    function hashWindow() {
        var b = sessionStorage.getItem('tduo.timeline.buttonH') || '';
        var z = sessionStorage.getItem('tduo.timeline.zoomPct') || '';
        var r = sessionStorage.getItem('tduo.retroview.endTs')  || '';
        var live = r ? '' : ('|live-' + Math.floor(Date.now() / 30000));
        return 'tl-' + b + '-' + z + '|rv-' + r + live;
    }
    var _lastWinHash = hashWindow();
    window.__tbChartPac.poller = setInterval(function() {
        var h = hashWindow();
        if (h !== _lastWinHash) { _lastWinHash = h; fetchSeries(); }
    }, 1000);

    // Subscribe to widget timewindow observable for instant updates
    try {
        if (ctxRef && ctxRef.defaultSubscription && ctxRef.defaultSubscription.widgetTimewindowChanged$) {
            window.__tbChartPac.sub = ctxRef.defaultSubscription.widgetTimewindowChanged$.subscribe(function() {
                _lastWinHash = hashWindow();
                fetchSeries();
            });
        }
    } catch (_e) {}

    window.__tbChartPac.listener = onMouseMove;
    document.addEventListener('mousemove', onMouseMove);
    window.__tbChartPac.interval = setInterval(fetchSeries, REFRESH_MS);

    // Redraw on container resize (responsive ticks/labels)
    try {
        var svgEl = document.getElementById('chart-svg-pac');
        if (svgEl && svgEl.parentElement && typeof ResizeObserver !== 'undefined') {
            var ro = new ResizeObserver(function() { drawChart(); });
            ro.observe(svgEl.parentElement);
            window.__tbChartPac.ro = ro;
        }
    } catch (_e) {}

    fetchSeries();
}, 200);

return html;
