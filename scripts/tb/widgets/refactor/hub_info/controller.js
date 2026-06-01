// scripts/tb/widgets/refactor/hub_info/controller.js
//
// Widget Hub Info refactored to read pac_v2 json_v (single timeseries key).
// Modes:
//   - hero (default) : page detail header avec KPIs (nHp, tExt, press) + sub-title (id, rel, time)
//   - det            : header de page detail HP (T.ext, P)
//
// Source de verite : spec docs/superpowers/specs/2026-05-28-payload-v2-pac-hybride-design.md
//                    Section 7.3 "default" -> Hub Info v2

self.onInit = function() {
    var ctx = self.ctx;
    var mode = (ctx.settings && ctx.settings.mode) || 'hero';
    self._mode = mode;
    ctx.$container.addClass('hub-info-host mode-' + mode);
    if (mode === 'hero') {
        ctx.$container.html(
            "<div class='hero'>" +
            "  <div class='h-left'>" +
            "    <div class='h-title'>Supervision TDUO <span class='brand'>Yahtec</span></div>" +
            "    <div class='h-sub' id='hero-sub'>—</div>" +
            "  </div>" +
            "  <div class='h-grid'>" +
            "    <div class='h-kpi'><div class='h-l'>TDUOs actifs</div><div class='h-v'><span id='hero-nhp'>—</span><span class='h-u'>/ 4</span></div></div>" +
            "    <div class='h-kpi'><div class='h-l'>Température ext.</div><div class='h-v'><span id='hero-text'>—</span><span class='h-u'>°C</span></div></div>" +
            "    <div class='h-kpi'><div class='h-l'>Pression réseau</div><div class='h-v'><span id='hero-press'>—</span><span class='h-u'>bar</span></div></div>" +
            "  </div>" +
            "</div>"
        );
    } else {
        ctx.$container.html(
            "<div class='det-head'>" +
            "  <a class='back' id='det-back'>← Retour</a>" +
            "  <div class='det-title'>Détail TDUO <span class='idx' id='det-idx'>—</span></div>" +
            "  <div class='det-chip' id='det-chip'>—</div>" +
            "  <div class='det-spacer'></div>" +
            "  <div class='det-kpi'><span class='l'>T.ext</span><span class='v'><span id='det-text'>—</span>°C</span></div>" +
            "  <div class='det-kpi'><span class='l'>P</span><span class='v'><span id='det-press'>—</span> bar</span></div>" +
            "</div>"
        );
        var sp = ctx.stateController ? ctx.stateController.getStateParams() : {};
        var idx = (sp && sp.hpIndex) ? sp.hpIndex : 1;
        var name = (sp && sp.tduoName) ? sp.tduoName : ('TDUO-' + idx);
        document.getElementById('det-idx').textContent = idx;
        document.getElementById('det-chip').textContent = name;
        document.getElementById('det-back').onclick = function() {
            ctx.stateController.navigatePrevState(ctx.stateController.getStateIndex());
        };
    }
};

function f(v, d){
    if (v === null || v === undefined || v === '') return '—';
    var n = Number(v);
    if (isNaN(n)) return v;
    if (n <= -99) return '—';
    return (d !== undefined) ? n.toFixed(d) : n;
}

function getPacV2(ctx) {
    var pacV2 = null;
    ctx.data.forEach(function(d){
        if (d.dataKey && d.dataKey.name === 'pac_v2' && d.data && d.data.length) {
            var raw = d.data[d.data.length - 1][1];
            try {
                pacV2 = (typeof raw === 'string') ? JSON.parse(raw) : raw;
            } catch (e) {
                pacV2 = null;
            }
        }
    });
    return pacV2;
}

self.onDataUpdated = function() {
    var p = getPacV2(self.ctx);
    if (!p) return;
    if (self._mode === 'hero') {
        document.getElementById('hero-nhp').textContent   = f(p.nHp, 0);
        document.getElementById('hero-text').textContent  = f(p.tExt, 1);
        document.getElementById('hero-press').textContent = f(p.press, 2);
        var rel = (p.rel !== null && p.rel !== undefined) ? p.rel : '—';
        var id = (p.id !== null && p.id !== undefined) ? p.id : '—';
        var t = p.time || '—';
        document.getElementById('hero-sub').innerHTML =
            'Hub <code>' + id + '</code> · firmware ' + rel + ' · dernière trame ' + t;
    } else {
        document.getElementById('det-text').textContent  = f(p.tExt, 1);
        document.getElementById('det-press').textContent = f(p.press, 2);
    }
};

self.onResize = function(){};
