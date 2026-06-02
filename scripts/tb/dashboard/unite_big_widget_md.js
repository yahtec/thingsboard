// Markdown/HTML value function — state "default" (titre "Unité")
// Rendu identique au précédent, mais :
//   - plus de dépendance au widget 2ed70b47 (qui définissait window.navState_*)
//   - nav via URL pushState (pattern w1_pac_info.js) câblée en event delegation sur document,
//     pour survivre aux re-renders liés aux changements de breakpoint desktop/mobile
//   - blocs PAC utilisent data-hp au lieu de onclick inline
//   - target state : toujours 'donnees_HP1' avec hpIndex en param (les widgets détail lisent hpIndex)

var e = data[0] || {};

var STATUS_HP = {
    '0': { label: 'Arret', color: '#9e9e9e' },
    '1': { label: 'Attente debit eau', color: '#fb8c00' },
    '2': { label: 'Init detendeur', color: '#fb8c00' },
    '3': { label: 'Demarrage compr.', color: '#fb8c00' },
    '4': { label: 'En service', color: '#43a047' },
    '5': { label: 'Defaut', color: '#e53935' },
    '6': { label: 'Defaut gaz', color: '#e53935' },
    '7': { label: 'Anti court-cycle', color: '#fb8c00' },
    '8': { label: 'Arret en cours', color: '#fb8c00' },
    '9': { label: 'Degivrage', color: '#1e88e5' },
    '10': { label: 'Pump down', color: '#fb8c00' }
};

var STATUS_BOIL = {
    '0': { label: 'Arret', color: '#9e9e9e' },
    '1': { label: 'Attente debit eau', color: '#fb8c00' },
    '2': { label: 'Preventilation', color: '#fb8c00' },
    '3': { label: 'Preventilation', color: '#fb8c00' },
    '4': { label: 'Preventilation', color: '#fb8c00' },
    '5': { label: 'En service', color: '#43a047' },
    '6': { label: 'Attente redemar.', color: '#fb8c00' },
    '7': { label: 'Stop maxi SD', color: '#e53935' },
    '8': { label: 'Defaut', color: '#e53935' },
    '9': { label: 'Nouveau cycle', color: '#fb8c00' },
    '10': { label: 'Defaut gaz', color: '#e53935' }
};

var TYPE_LABELS = {
    '0': 'Sans module',
    '1': 'Chauffage',
    '2': 'ECS',
    '3': 'Chauffage + ECS'
};

function gs(map, val) {
    var s = map[String(val)];
    return s || { label: 'Code ' + val, color: '#9e9e9e' };
}
function badge(map, val) {
    var s = gs(map, val);
    return '<span class="badge" style="background:' + s.color + '">' + s.label + '</span>';
}
function fv(val, unit) {
    if (val === null || val === undefined || val === '') return '--';
    var n = parseFloat(val);
    return isNaN(n) ? '--' : n.toFixed(1) + (unit || '');
}
function debit(val) {
    var lh = parseFloat(val || 0);
    if (isNaN(lh)) lh = 0;
    return (lh / 1000).toFixed(2) + ' m3/h';
}
function row(label, val) {
    return '<div class="data-row"><span class="dl">' + label + '</span><span class="dv">' + val + '</span></div>';
}
function rowT(label, val, cls) {
    return '<div class="data-row"><span class="dl">' + label + '</span><span class="dv ' + cls + '">' + fv(val, ' C') + '</span></div>';
}

function buildPAC(e, n) {
    var p = 'HP' + n + '_';
    var h = '';
    h += '<div class="bloc pac-bloc" data-hp="' + n + '" role="button" tabindex="0" aria-label="Voir details PAC ' + n + '">';
    h += '<div class="bloc-title">PAC Hybride n' + n + '</div>';
    h += '<div class="bloc-body">';
    h += '<div class="section-label">Pompe a chaleur</div>';
    h += row('Statut', badge(STATUS_HP, e[p + 'status']));
    h += rowT('T entree', e[p + 'tIn'], 'temp-blue');
    h += rowT('T sortie PAC', e[p + 'tOut'], 'temp-red');
    h += row('Frequence', fv(e[p + 'invert_freq'], ' Hz'));
    h += '<div class="separator"></div>';
    h += '<div class="section-label">Chaudiere</div>';
    h += row('Statut', badge(STATUS_BOIL, e[p + 'boil_status']));
    h += rowT('T entree', e[p + 'tOut'], 'temp-blue');
    h += rowT('T sortie', e[p + 'boil_tOut'], 'temp-red');
    h += row('Vitesse bruleur', fv(e[p + 'boil_rpm'], ' rpm'));
    h += '<div class="separator"></div>';
    h += '<div class="section-label">Module</div>';
    h += row('Debit eau', debit(e[p + 'boil_qe']));
    h += '<div class="detail-link">Voir détails →</div>';
    h += '</div></div>';
    return h;
}

function buildECS(e) {
    var h = '';
    h += '<div class="bloc ecs-bloc">';
    h += '<div class="bloc-title">Module ECS</div>';
    h += '<div class="bloc-body">';
    h += rowT('T depart', e['dhw_tOut'], 'temp-red');
    h += rowT('T retour', e['dhw_tIn'], 'temp-blue');
    h += rowT('T ballon', e['dhw_tTank'], '');
    h += row('Consigne', fv(e['dhw_tSet'], ' C'));
    h += '</div></div>';
    return h;
}

function buildChauffage(e) {
    var h = '';
    h += '<div class="bloc heat-bloc">';
    h += '<div class="bloc-title">Module Chauffage</div>';
    h += '<div class="bloc-body">';
    h += rowT('T depart', e['heat_tOut'], 'temp-red');
    h += rowT('T retour', e['heat_tIn'], 'temp-blue');
    h += row('Consigne', fv(e['heat_setpoint'], ' C'));
    h += row('Position V3V', fv(e['heat_posV3V'], ' %'));
    h += '</div></div>';
    return h;
}

var nHp = parseInt(e['nHp'] || 1);
var type = parseInt(e['type'] || 0);

var _entName = (data[0] && data[0].entityName) || '--';
window.__tduoInstallName = _entName;
var _entLabel = (data[0] && data[0].entityLabel) || '';

var html = '<div class="schema-page">';


// Navbar : widget separe (Navbar HTML Card row=0). Le handler click/keydown
// ci-dessous ecoute [data-navtarget] au niveau document, donc capte aussi les
// clics emis par le widget navbar - meme s'il est remonte independamment.

html += '<div class="schema-body">';

html += '<div class="col-left">';
html += '<div class="common-title">Données générales</div>';
html += '<div class="common-row"><span class="common-label">Date</span><span class="common-value">' + (e['date'] || '--') + '</span></div>';
html += '<div class="common-row"><span class="common-label">Heure</span><span class="common-value">' + (e['time'] || '--') + '</span></div>';
html += '<div class="common-row"><span class="common-label">T° extérieure</span><span class="common-value">' + fv(e['tExt'], ' C') + '</span></div>';
html += '<div class="common-row"><span class="common-label">Pression</span><span class="common-value">' + fv(e['press'], ' bar') + '</span></div>';
html += '<div class="common-row"><span class="common-label">Nb PAC</span><span class="common-value">' + (e['nHp'] || '--') + '</span></div>';
html += '<div class="common-row"><span class="common-label">Configuration</span><span class="common-value">' + (TYPE_LABELS[String(type)] || '--') + '</span></div>';
html += '</div>';

html += '<div class="col-right"><div class="schema-scroll">';
for (var i = 1; i <= nHp; i++) {
    html += buildPAC(e, i);
}
if (type === 2 || type === 3) {
    html += buildECS(e);
}
if (type === 1 || type === 3) {
    html += buildChauffage(e);
}
html += '</div></div>';  // /.schema-scroll, /.col-right
html += '</div>';  // /.schema-body
html += '</div>';  // /.schema-page

// Event delegation : on attache un unique listener au document (survit aux re-renders
// markdown lors des changements desktop/mobile). Le flag evite les doublons.
setTimeout(function() {
    if (window.__tduoDefaultNavWired) return;
    window.__tduoDefaultNavWired = true;

    function getCurrentEntityIdParam() {
        // Lit l'entityId du state actuel dans l'URL — propagation indispensable
        // pour que les widgets de donnees_HP1 (alias Chaufferie sélectionnée,
        // type stateEntity) résolvent vers le bon device. Sinon ils retombent
        // sur defaultStateEntity = Yahtec.
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

    function goState(stateId, params) {
        var p = Object.assign({}, params || {});
        if (!p.entityId) {
            var eid = getCurrentEntityIdParam();
            if (eid) p.entityId = eid;
        }
        var stateB64 = btoa(JSON.stringify([{ id: stateId, params: p }]));
        window.history.pushState({}, '', window.location.pathname + '?state=' + encodeURIComponent(stateB64));
        var evt = document.createEvent('Event');
        evt.initEvent('popstate', true, true);
        window.dispatchEvent(evt);
    }

    function navPac(n) {
        // Target state fixe donnees_HP1, hpIndex en param : les widgets detail
        // (w1_pac_info, w2_pac_chart, w3_boiler_info, w4_boiler_chart) lisent hpIndex
        goState('donnees_HP1', { hpIndex: n, hp: n });
    }

    document.addEventListener('click', function(ev) {
        var t = ev.target;
        if (!t || !t.closest) return;
        var navEl = t.closest('[data-navtarget]');
        if (navEl) {
            ev.preventDefault();
            goState(navEl.getAttribute('data-navtarget'));
            return;
        }
        var bloc = t.closest('.pac-bloc[data-hp]');
        if (!bloc) return;
        var n = parseInt(bloc.getAttribute('data-hp'), 10);
        if (!n) return;
        ev.preventDefault();
        navPac(n);
    });

    // Accessibilite clavier (Enter / Space)
    document.addEventListener('keydown', function(ev) {
        if (ev.key !== 'Enter' && ev.key !== ' ') return;
        var t = ev.target;
        if (!t || !t.classList) return;
        if (t.classList.contains('pac-bloc')) {
            var n = parseInt(t.getAttribute('data-hp'), 10);
            if (!n) return;
            ev.preventDefault();
            navPac(n);
            return;
        }
        if (t.hasAttribute && t.hasAttribute('data-navtarget')) {
            ev.preventDefault();
            goState(t.getAttribute('data-navtarget'));
        }
    });
}, 0);

return html;
