// scripts/tb/widgets/refactor/heating_loop_card/controller.js
//
// Widget Heating Loop Card refactored to read pac_v2 json_v.
// Affichage : circuit chauffage avec consigne/depart/retour/exterieur + V3V/loi-eau/pied/tMax/tCut.
// Mapping :
//   pac_v2.heat.setpoint  -> Consigne
//   pac_v2.heat.tOut      -> Depart (tDep)
//   pac_v2.heat.tIn       -> Retour (tRet)
//   pac_v2.tExt           -> Exterieur
//   pac_v2.heat.posV3V    -> V3V (jauge %)
//   pac_v2.heat.slope     -> Pente loi eau
//   pac_v2.heat.foot      -> Pied
//   pac_v2.heat.tMax      -> Tmax
//   pac_v2.heat.tCut      -> tCut (arret chauf.)

self.onInit = function() {
    var ctx = self.ctx;
    ctx.$container.addClass('heat-card-host');
    ctx.$container.html(
        "<div class='heat'>" +
        "  <div class='hh'><div class='ttl'>Circuit chauffage</div><div class='sub' id='heat-sub'>—</div></div>" +
        "  <div class='hm'>" +
        "    <div class='r'><div class='l'>Consigne</div><div class='v big' id='heat-set'>—</div><div class='u'>°C</div></div>" +
        "    <div class='r'><div class='l'>Départ</div><div class='v big' id='heat-tdep'>—</div><div class='u'>°C</div></div>" +
        "    <div class='r'><div class='l'>Retour</div><div class='v big' id='heat-tret'>—</div><div class='u'>°C</div></div>" +
        "    <div class='r'><div class='l'>Extérieur</div><div class='v big' id='heat-text'>—</div><div class='u'>°C</div></div>" +
        "  </div>" +
        "  <div class='hv'>" +
        "    <div class='x'><span class='k'>V3V</span><div class='bar'><div class='fill' id='heat-v3v-fill'></div></div><span class='v' id='heat-v3v'>—</span><span class='u'>%</span></div>" +
        "    <div class='x'><span class='k'>Loi d'eau (pente)</span><span class='v' id='heat-slope'>—</span></div>" +
        "    <div class='x'><span class='k'>Pied</span><span class='v' id='heat-foot'>—</span><span class='u'>°C</span></div>" +
        "    <div class='x'><span class='k'>T. max</span><span class='v' id='heat-tmax'>—</span><span class='u'>°C</span></div>" +
        "    <div class='x'><span class='k'>Arrêt chauf.</span><span class='v' id='heat-tcut'>—</span><span class='u'>°C</span></div>" +
        "  </div>" +
        "</div>"
    );
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
    var heat = p.heat || {};
    document.getElementById('heat-set').textContent  = f(heat.setpoint, 1);
    document.getElementById('heat-tdep').textContent = f(heat.tOut, 1);
    document.getElementById('heat-tret').textContent = f(heat.tIn, 1);
    document.getElementById('heat-text').textContent = f(p.tExt, 1);
    var v3v = Number(heat.posV3V || 0);
    document.getElementById('heat-v3v').textContent = f(v3v, 0);
    document.getElementById('heat-v3v-fill').style.width = Math.max(0, Math.min(100, v3v)) + '%';
    document.getElementById('heat-slope').textContent = f(heat.slope, 1);
    document.getElementById('heat-foot').textContent  = f(heat.foot, 0);
    document.getElementById('heat-tmax').textContent  = f(heat.tMax, 0);
    document.getElementById('heat-tcut').textContent  = f(heat.tCut, 0);
    document.getElementById('heat-sub').textContent = 'Consigne ' + f(heat.setpoint, 1) + ' °C';
};

self.onResize = function(){};
