// scripts/tb/widgets/refactor/boiler_synoptic/controller.js
//
// Widget Boiler Synoptic refactored to read pac_v2 json_v.
// Multi-instance : hpIndex (1..4) via settings ou stateController.getStateParams().
// Mapping (HP{N}_boil_*  ->  pac_v2.HPs[hpIndex-1].boil.*) :
//   .status   -> code (BOIL_STATE table)
//   .rpm      -> Allure
//   .tOut     -> T. depart
//   .tSmoke   -> T. fumees
//   .press    -> Pression
//   .qe       -> Debit
//   .time     -> Duree marche

self.onInit = function() {
    var ctx = self.ctx;
    var idx = getIdx(ctx);
    self._idx = idx;
    ctx.$container.addClass('boil-synoptic-host');
    ctx.$container.html(
        "<div class='boil'>" +
        "  <div class='bh'><div class='ttl'>Chaudière</div><div class='sub' id='boil-sub'>TDUO-" + idx + "</div><div class='st' id='boil-st'><span class='dot'></span><span class='txt'>—</span></div></div>" +
        "  <div class='bm'>" +
        "    <div class='bn'><div class='l'>Allure</div><div class='v big' id='boil-rpm'>—</div><div class='u'>rpm</div></div>" +
        "    <div class='bn'><div class='l'>T. départ</div><div class='v big' id='boil-tout'>—</div><div class='u'>°C</div></div>" +
        "    <div class='bn flame'><div class='flicon' id='boil-flic'>🔥</div><div class='v' id='boil-state'>—</div></div>" +
        "    <div class='bn'><div class='l'>T. fumées</div><div class='v big' id='boil-tsmoke'>—</div><div class='u'>°C</div></div>" +
        "    <div class='bn'><div class='l'>Pression</div><div class='v big' id='boil-press'>—</div><div class='u'>bar</div></div>" +
        "  </div>" +
        "  <div class='bx'>" +
        "    <div class='x'><span class='k'>Débit</span><span class='v' id='boil-qe'>—</span><span class='u'>L/h</span></div>" +
        "    <div class='x'><span class='k'>Durée marche</span><span class='v' id='boil-time'>—</span><span class='u'>h</span></div>" +
        "    <div class='x'><span class='k'>Code état</span><span class='v' id='boil-scode'>—</span></div>" +
        "  </div>" +
        "</div>"
    );
};

function getIdx(ctx) {
    if (ctx.stateController) {
        var sp = ctx.stateController.getStateParams();
        if (sp && sp.hpIndex) return Number(sp.hpIndex);
    }
    if (ctx.settings && ctx.settings.hpIndex) return Number(ctx.settings.hpIndex);
    return 1;
}

function f(v, d) {
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

var BOIL_STATE = {
    0: 'Arrêt', 5: 'En marche', 10: 'Veille', 20: 'Pré-ventilation', 25: 'Allumage', 30: 'En marche',
    35: 'Post-ventilation', 40: 'Défaut allumage', 50: 'Défaut flamme', 60: 'Surchauffe'
};

self.onDataUpdated = function() {
    var ctx = self.ctx, idx = self._idx;
    var p = getPacV2(ctx);
    if (!p) return;
    var hps = Array.isArray(p.HPs) ? p.HPs : [];
    var hp = hps[idx - 1] || {};
    var boil = hp.boil || {};
    var comm = hp.comm;
    var st = Number(boil.status || 0);
    var rpm = Number(boil.rpm || 0);
    var cls = (comm === true || comm === 'true') ? (st >= 40 ? 'bad' : (rpm > 10 || st === 5 || st === 30) ? 'ok' : 'idle') : 'off';
    var stEl = document.getElementById('boil-st');
    stEl.className = 'st ' + cls;
    var lbl = BOIL_STATE[st] !== undefined ? BOIL_STATE[st] : 'État ' + st;
    stEl.querySelector('.txt').textContent = cls === 'off' ? 'Hors ligne' : lbl;

    document.getElementById('boil-rpm').textContent    = f(boil.rpm, 0);
    document.getElementById('boil-tout').textContent   = f(boil.tOut, 1);
    document.getElementById('boil-tsmoke').textContent = f(boil.tSmoke, 1);
    document.getElementById('boil-press').textContent  = f(boil.press, 2);
    document.getElementById('boil-qe').textContent     = f(boil.qe, 0);
    document.getElementById('boil-time').textContent   = f(boil.time, 0);
    document.getElementById('boil-scode').textContent  = st;
    document.getElementById('boil-state').textContent  = lbl;
    document.getElementById('boil-flic').className = 'flicon ' + (cls === 'ok' ? 'on' : cls === 'bad' ? 'bad' : 'off');
    document.getElementById('boil-sub').textContent = 'TDUO-' + idx;
};
self.onResize = function() {};
