// scripts/tb/widgets/refactor/tduo_tile/controller.js
//
// Widget TDUO Tile refactored to read pac_v2 json_v + asset attributes (address/label).
// Tuile parc : etat global (PAC + Chaudiere) + T.dep + Pression + nav vers detail.
// Mapping (HP{hpIndex}_* -> pac_v2.HPs[hpIndex-1].*) :
//   .comm                 -> liaison
//   .HP.status            -> code etat PAC (6 = defaut)
//   .invert.{freq,pwr}    -> Inverter Hz + W
//   .boil.{status,rpm,tOut} -> Chaudiere
//   .HP.{tOut,tIn,pHi,pLo} -> Eau / pressions
// Asset (datasource secondary) :
//   address / label       -> Location displayed in tile

self.onInit = function() {
    var ctx = self.ctx;
    var idx = (ctx.settings && ctx.settings.hpIndex) ? ctx.settings.hpIndex : 1;
    ctx.$container.addClass('tduo-tile-host');
    ctx.$container.html(
        "<div class='tduo-tile' data-idx='" + idx + "'>" +
        "  <div class='tt-head'>" +
        "    <div class='tt-label'><span class='tt-chip'>TDUO-" + idx + "</span><span class='tt-loc' id='tt-loc-" + idx + "'>—</span></div>" +
        "    <div class='tt-state' id='tt-state-" + idx + "'><span class='dot'></span><span class='txt'>—</span></div>" +
        "  </div>" +
        "  <div class='tt-body'>" +
        "    <div class='tt-cell'><div class='l'>PAC</div><div class='v' id='tt-pac-" + idx + "'>—</div><div class='s' id='tt-pac-sub-" + idx + "'>—</div></div>" +
        "    <div class='tt-cell'><div class='l'>Chaudière</div><div class='v' id='tt-boil-" + idx + "'>—</div><div class='s' id='tt-boil-sub-" + idx + "'>—</div></div>" +
        "    <div class='tt-cell'><div class='l'>T. dép.</div><div class='v big' id='tt-tout-" + idx + "'>—<span class='u'>°C</span></div><div class='s' id='tt-tin-" + idx + "'>—</div></div>" +
        "    <div class='tt-cell'><div class='l'>Pression</div><div class='v big' id='tt-phi-" + idx + "'>—<span class='u'>bar</span></div><div class='s' id='tt-plo-" + idx + "'>—</div></div>" +
        "  </div>" +
        "  <div class='tt-foot'><span class='tt-open'>Voir le détail ›</span></div>" +
        "</div>"
    );
    ctx.$container.find('.tduo-tile').on('click', function(e) {
        var descriptors = ctx.actionsApi.getActionDescriptors('elementClick');
        if (descriptors && descriptors.length) {
            ctx.actionsApi.onWidgetAction(e, descriptors[0]);
        }
    });
    self._idx = idx;
};

function fmt(v, dec) {
    if (v === null || v === undefined || v === '') return '—';
    var n = Number(v);
    if (isNaN(n)) return v;
    if (n <= -99) return '—';
    return (dec !== undefined) ? n.toFixed(dec) : n;
}

function getPacV2(ctx) {
    var pacV2 = null;
    var assetAttrs = {};
    ctx.data.forEach(function(d){
        if (!d.dataKey || !d.data || !d.data.length) return;
        var name = d.dataKey.name;
        var val = d.data[d.data.length - 1][1];
        if (name === 'pac_v2') {
            try { pacV2 = (typeof val === 'string') ? JSON.parse(val) : val; }
            catch (e) { pacV2 = null; }
        } else if (name === 'address' || name === 'label') {
            assetAttrs[name] = val;
        }
    });
    return { pac: pacV2, asset: assetAttrs };
}

function pacState(hp) {
    var comm = hp.comm;
    var st = Number((hp.HP || {}).status || 0);
    var freq = Number((hp.invert || {}).freq || 0);
    if (comm !== true && comm !== 'true') return {cls:'off', lbl:'Hors ligne'};
    if (st === 6) return {cls:'bad', lbl:'Défaut'};
    if (freq > 1) return {cls:'ok', lbl:'En marche'};
    return {cls:'idle', lbl:'Veille'};
}
function boilState(hp) {
    var comm = hp.comm;
    var boil = hp.boil || {};
    var st = Number(boil.status || 0);
    var rpm = Number(boil.rpm || 0);
    if (comm !== true && comm !== 'true') return {cls:'off', lbl:'Hors ligne'};
    if (st >= 40) return {cls:'bad', lbl:'Défaut'};
    if (rpm > 10 || st === 5 || st === 30) return {cls:'ok', lbl:'En marche'};
    if (st === 10) return {cls:'idle', lbl:'Veille'};
    return {cls:'idle', lbl:'Arrêt'};
}

self.onDataUpdated = function() {
    var ctx = self.ctx, idx = self._idx;
    var collected = getPacV2(ctx);
    var p = collected.pac;
    if (!p) return;
    var hps = Array.isArray(p.HPs) ? p.HPs : [];
    var hp = hps[idx - 1] || {};
    var hpData = hp.HP || {};
    var invert = hp.invert || {};
    var boil = hp.boil || {};

    // location from asset datasource if present
    var locEl = document.getElementById('tt-loc-' + idx);
    if (collected.asset.address) locEl.textContent = collected.asset.address;
    else if (collected.asset.label) locEl.textContent = collected.asset.label;

    var pac = pacState(hp);
    var boilSt = boilState(hp);
    var globalCls = (pac.cls === 'bad' || boilSt.cls === 'bad') ? 'bad'
                  : (pac.cls === 'off' && boilSt.cls === 'off') ? 'off'
                  : (pac.cls === 'ok' || boilSt.cls === 'ok') ? 'ok'
                  : 'idle';
    var state = document.getElementById('tt-state-' + idx);
    state.className = 'tt-state ' + globalCls;
    state.querySelector('.txt').textContent =
        globalCls === 'ok' ? 'Actif' :
        globalCls === 'bad' ? 'Défaut' :
        globalCls === 'off' ? 'Hors ligne' : 'Veille';

    document.getElementById('tt-pac-' + idx).textContent = pac.lbl;
    document.getElementById('tt-pac-' + idx).className = 'v st-' + pac.cls;
    document.getElementById('tt-pac-sub-' + idx).textContent =
        fmt(invert.freq, 1) + ' Hz • ' + fmt(invert.pwr, 0) + ' W';

    document.getElementById('tt-boil-' + idx).textContent = boilSt.lbl;
    document.getElementById('tt-boil-' + idx).className = 'v st-' + boilSt.cls;
    document.getElementById('tt-boil-sub-' + idx).textContent =
        fmt(boil.tOut, 1) + ' °C • ' + fmt(boil.rpm, 0) + ' rpm';

    document.getElementById('tt-tout-' + idx).innerHTML =
        fmt(hpData.tOut, 1) + '<span class="u">°C</span>';
    document.getElementById('tt-tin-' + idx).textContent =
        'Retour ' + fmt(hpData.tIn, 1) + ' °C';

    document.getElementById('tt-phi-' + idx).innerHTML =
        fmt(hpData.pHi, 1) + '<span class="u">bar</span>';
    document.getElementById('tt-plo-' + idx).textContent =
        'BP ' + fmt(hpData.pLo, 1) + ' bar';
};

self.onResize = function() {};
self.onDestroy = function() {};
