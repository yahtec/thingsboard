// scripts/tb/widgets/refactor/dhw_card/controller.js
//
// Widget DHW Card refactored to read pac_v2 json_v.
// Affichage : ballon ECS (jauge + consigne) + 5 KPIs (Consigne, Entrée, Sortie, Pompe1, Pompe2).
// Mapping :
//   pac_v2.dhw.tTank  -> tank (jauge + valeur)
//   pac_v2.dhw.tSet   -> consigne (ligne sur jauge + valeur)
//   pac_v2.dhw.tIn    -> Entrée
//   pac_v2.dhw.tOut   -> Sortie
//   pac_v2.dhw.pump1.rpm / pump2.rpm -> Pompes

self.onInit = function() {
    var ctx = self.ctx;
    ctx.$container.addClass('dhw-card-host');
    ctx.$container.html(
        "<div class='dhw'>" +
        "  <div class='hh'><div class='ttl'>ECS · Eau chaude sanitaire</div><div class='sub' id='dhw-sub'>—</div></div>" +
        "  <div class='dhw-body'>" +
        "    <div class='tank'>" +
        "      <div class='tank-bar'><div class='fill' id='dhw-fill'></div><div class='set' id='dhw-set-line'></div></div>" +
        "      <div class='tank-legend'><span id='dhw-tank'>—</span>°C</div>" +
        "    </div>" +
        "    <div class='dm'>" +
        "      <div class='m'><div class='l'>Consigne</div><div class='v' id='dhw-sett'>—</div><div class='u'>°C</div></div>" +
        "      <div class='m'><div class='l'>Entrée</div><div class='v' id='dhw-tin'>—</div><div class='u'>°C</div></div>" +
        "      <div class='m'><div class='l'>Sortie</div><div class='v' id='dhw-tout'>—</div><div class='u'>°C</div></div>" +
        "      <div class='m'><div class='l'>Pompe 1</div><div class='v' id='dhw-p1'>—</div><div class='u'>rpm</div></div>" +
        "      <div class='m'><div class='l'>Pompe 2</div><div class='v' id='dhw-p2'>—</div><div class='u'>rpm</div></div>" +
        "    </div>" +
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
    var dhw = p.dhw || {};
    var pump1 = dhw.pump1 || {};
    var pump2 = dhw.pump2 || {};
    var tankRaw = dhw.tTank;
    var setRaw  = dhw.tSet;
    var tank = (tankRaw !== null && tankRaw !== undefined && tankRaw !== '') ? Number(tankRaw) : null;
    var set  = (setRaw  !== null && setRaw  !== undefined && setRaw  !== '') ? Number(setRaw)  : null;
    var pct  = (tank !== null && !isNaN(tank) && tank > -99) ? Math.max(0, Math.min(100, (tank / 80) * 100)) : 0;
    var setP = (set  !== null && !isNaN(set)  && set  > -99) ? Math.max(0, Math.min(100, (set  / 80) * 100)) : 0;
    document.getElementById('dhw-fill').style.height = pct + '%';
    document.getElementById('dhw-set-line').style.bottom = setP + '%';
    document.getElementById('dhw-tank').textContent = f(tank, 1);
    document.getElementById('dhw-sett').textContent = f(set,  0);
    document.getElementById('dhw-tin').textContent  = f(dhw.tIn, 1);
    document.getElementById('dhw-tout').textContent = f(dhw.tOut, 1);
    document.getElementById('dhw-p1').textContent   = f(pump1.rpm, 0);
    document.getElementById('dhw-p2').textContent   = f(pump2.rpm, 0);
    document.getElementById('dhw-sub').textContent = 'Ballon ' + f(tankRaw, 1) + ' °C / consigne ' + f(setRaw, 0) + ' °C';
};

self.onResize = function(){};
