// scripts/tb/widgets/refactor/pac_synoptic/controller.js
//
// Widget PAC Synoptic refactored to read pac_v2 json_v.
// Multi-instance : hpIndex (1..4) via settings ou stateController.getStateParams().
// Mapping :
//   pac_v2.HPs[hpIndex-1].comm          -> status comm
//   pac_v2.HPs[hpIndex-1].HP.status     -> status code (6 = defaut)
//   pac_v2.HPs[hpIndex-1].HP.tCond      -> Condenseur
//   pac_v2.HPs[hpIndex-1].HP.tEvap      -> Evaporateur
//   pac_v2.HPs[hpIndex-1].HP.tOut       -> Depart eau
//   pac_v2.HPs[hpIndex-1].HP.tIn        -> Retour eau
//   pac_v2.HPs[hpIndex-1].HP.pHi/.pLo   -> HP/BP
//   pac_v2.HPs[hpIndex-1].invert.{freq,pwr,curr,volt} -> Inverter
//   pac_v2.tExt (TOP-LEVEL)             -> Air exterieur (le flat HP{N}_tAir n'existait pas)

self.onInit = function() {
    var ctx = self.ctx;
    var idx = getIdx(ctx);
    self._idx = idx;
    ctx.$container.addClass('pac-synoptic-host');
    // Click navigation : si settings.navigateTo est defini (ex 'donnees_HP1'),
    // un clic sur la card empile cet etat avec hpIndex dans les state params.
    // Implementation via manipulation directe de l'URL (memes patterns que
    // l'Action button du dashboard 'Mes Installations' -- contournement du
    // bug TB sur openDashboardState dans cette version).
    var navTo = (ctx.settings && ctx.settings.navigateTo) || null;
    if (navTo) {
        ctx.$container.on('click', '.pacs', function() {
            try {
                var raw = new URL(window.location.href).searchParams.get('state');
                var arr = raw ? JSON.parse(atob(decodeURIComponent(raw))) : [];
                var entityId = null;
                for (var i = arr.length - 1; i >= 0; i--) {
                    var p = arr[i] && arr[i].params;
                    if (p && p.entityId && p.entityId.id) { entityId = p.entityId; break; }
                }
                var newParams = { hpIndex: idx };
                if (entityId) newParams.entityId = entityId;
                arr.push({ id: navTo, params: newParams });
                var b64 = btoa(JSON.stringify(arr));
                window.history.pushState({}, '', window.location.pathname + '?state=' + encodeURIComponent(b64));
                window.dispatchEvent(new Event('popstate'));
            } catch (e) { /* noop */ }
        });
        ctx.$container.css('cursor', 'pointer');
    }
    ctx.$container.html(
        "<div class='pacs'>" +
        "  <div class='pacs-head'><div class='ttl'>Pompe à chaleur</div><div class='sub' id='pacs-sub'>TDUO-" + idx + "</div><div class='st' id='pacs-st'><span class='dot'></span><span class='txt'>—</span></div></div>" +
        "  <div class='pacs-grid'>" +
        "    <div class='node in'><div class='lbl'>Air ext.</div><div class='val' id='pacs-tair'>—</div><div class='sub'>°C ext.</div></div>" +
        "    <div class='arrow'></div>" +
        "    <div class='node evap'><div class='lbl'>Évaporateur</div><div class='val' id='pacs-tevap'>—</div><div class='sub'>T évap.</div></div>" +
        "    <div class='arrow'></div>" +
        "    <div class='node comp'><div class='lbl'>Compresseur</div><div class='val' id='pacs-freq'>—</div><div class='sub'>Hz</div><div class='xtr' id='pacs-pwr'>— W</div></div>" +
        "    <div class='arrow'></div>" +
        "    <div class='node cond'><div class='lbl'>Condenseur</div><div class='val' id='pacs-tcond'>—</div><div class='sub'>T cond.</div></div>" +
        "    <div class='arrow'></div>" +
        "    <div class='node out'><div class='lbl'>Départ eau</div><div class='val big' id='pacs-tout'>—</div><div class='sub'>°C</div></div>" +
        "  </div>" +
        "  <div class='pacs-metrics'>" +
        "    <div class='m'><div class='l'>HP</div><div class='v' id='pacs-phi'>—</div><div class='u'>bar</div></div>" +
        "    <div class='m'><div class='l'>BP</div><div class='v' id='pacs-plo'>—</div><div class='u'>bar</div></div>" +
        "    <div class='m'><div class='l'>ΔT évap→cond</div><div class='v' id='pacs-dt'>—</div><div class='u'>°C</div></div>" +
        "    <div class='m'><div class='l'>Courant</div><div class='v' id='pacs-curr'>—</div><div class='u'>A</div></div>" +
        "    <div class='m'><div class='l'>Tension</div><div class='v' id='pacs-volt'>—</div><div class='u'>V</div></div>" +
        "    <div class='m'><div class='l'>Retour eau</div><div class='v' id='pacs-tin'>—</div><div class='u'>°C</div></div>" +
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

self.onDataUpdated = function() {
    var ctx = self.ctx, idx = self._idx;
    var p = getPacV2(ctx);
    if (!p) return;
    var hps = Array.isArray(p.HPs) ? p.HPs : [];
    var hp = hps[idx - 1] || {};
    var hpData = hp.HP || {};
    var invert = hp.invert || {};
    var comm = hp.comm;
    var st = Number(hpData.status || 0);
    var freq = Number(invert.freq || 0);
    var stEl = document.getElementById('pacs-st');
    var cls = (comm === true || comm === 'true') ? (st === 6 ? 'bad' : (freq > 1 ? 'ok' : 'idle')) : 'off';
    stEl.className = 'st ' + cls;
    stEl.querySelector('.txt').textContent =
        cls === 'ok' ? 'En marche' : cls === 'bad' ? 'Défaut' : cls === 'off' ? 'Hors ligne' : 'Veille';

    // Air ext. : on lit pac_v2.tExt (top-level) -- HP{N}_tAir n'existait pas en flat
    document.getElementById('pacs-tair').textContent  = f(p.tExt, 1);
    document.getElementById('pacs-tevap').textContent = f(hpData.tEvap, 1);
    document.getElementById('pacs-tcond').textContent = f(hpData.tCond, 1);
    document.getElementById('pacs-tout').textContent  = f(hpData.tOut, 1);
    document.getElementById('pacs-tin').textContent   = f(hpData.tIn, 1);
    document.getElementById('pacs-freq').textContent  = f(invert.freq, 1);
    document.getElementById('pacs-pwr').textContent   = f(invert.pwr, 0) + ' W';
    document.getElementById('pacs-phi').textContent   = f(hpData.pHi, 2);
    document.getElementById('pacs-plo').textContent   = f(hpData.pLo, 2);
    document.getElementById('pacs-curr').textContent  = f(invert.curr, 1);
    document.getElementById('pacs-volt').textContent  = f(invert.volt, 0);
    var tc = Number(hpData.tCond), te = Number(hpData.tEvap);
    document.getElementById('pacs-dt').textContent = (isFinite(tc) && isFinite(te) && tc > -99 && te > -99) ? (tc - te).toFixed(1) : '—';
    document.getElementById('pacs-sub').textContent = 'TDUO-' + idx + (cls === 'ok' ? ' · compresseur actif' : '');
};

self.onResize = function() {};
