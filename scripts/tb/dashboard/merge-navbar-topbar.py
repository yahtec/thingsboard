#!/usr/bin/env python3
"""
Fusion Navbar (a1b2c3d4...0010) + Topbar (a1b2c3d4...0001) en UN seul
bandeau unifie. Patche en place la Navbar (HTML+CSS+JS rewrite). Retire
la Topbar des layouts (mais garde le widget en stash pour rollback).

Bandeau cible : 2 lignes desktop, 1 ligne compact mobile.
  Row 1 : [Title TDUO <serial>]  Mes installations > <residence>
          Derniere donnee : <ts>
  Row 2 : [Retour] [QuitterRetro] [Defaut] [Param] | [Accueil] [Profil] [Comptes] [Logout]

Visibilite par state :
  menu          : title=TDUO chaufferies, no crumb, only Accueil(self)/Profil/Comptes/Logout
  default       : crumb+ts+Defaut+Param(admin)+Accueil/Profil/Comptes/Logout
  donnees_HP1   : crumb+ts+Retour(default)+Defaut+Param(admin)+Acc/Pro/Cpt/Out [+ QuitRetro if active]
  historique    : crumb+Retour(default)+Param(admin)+Acc/Pro/Cpt/Out (Defaut cache, on est dessus)
  fault_diagnostic : crumb+Retour(historique)+Param(admin)+Acc/Pro/Cpt/Out (Defaut cache)
  configuration : crumb+Retour(default)+Defaut+Acc/Pro/Cpt/Out (Param cache, on est dessus)
  profil        : crumb=Mon profil+Retour(prev)+Acc/Cpt/Out (Profil cache)
  notifications_admin : crumb=Comptes admin+Retour+Acc/Pro/Out (Comptes cache)

Conditional admin : Param + Comptes affiches uniquement si TENANT_ADMIN OU
  attribut user is_admin=true.

Idempotent via marker __MERGED_NAVBAR_V1__.
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
NAVBAR_ID    = 'a1b2c3d4-0100-4000-a000-000000000010'
TOPBAR_ID    = 'a1b2c3d4-0200-4000-a000-000000000001'
NAVBAR2BTN_ID = 'a1b2c3d4-0100-4000-a000-000000000020'
BASE_URL     = 'https://thingsboard.tsmart.fr'
MARKER       = '__MERGED_NAVBAR_V1__'

# Tous les states sur lesquels on veut le bandeau unifie
STATES_WITH_NAVBAR = ['menu', 'default', 'donnees_HP1', 'historique',
                     'fault_diagnostic', 'configuration', 'profil',
                     'notifications_admin']

MERGED_HTML = '''<!-- ''' + MARKER + ''' : bandeau unifie Topbar+Navbar -->
<nav class="tdb-bar" id="tdb-bar">
  <div class="tdb-row tdb-row-top">
    <div class="tdb-title" id="tdb-title">
      <a href="javascript:void(0)" data-navtarget="menu" class="tdb-title-link">
        <span class="tdb-title-text" id="tdb-title-text">TDUO</span>
      </a>
    </div>
    <div class="tdb-info">
      <div class="tdb-breadcrumb">
        <a href="javascript:void(0)" class="tdb-crumb-link" data-navtarget="menu">Mes installations</a>
        <span class="tdb-crumb-sep" id="tdb-crumb-sep">&rsaquo;</span>
        <span class="tdb-residence" id="tdb-residence"></span>
      </div>
      <div class="tdb-laststamp" id="tdb-laststamp"></div>
    </div>
  </div>
  <div class="tdb-row tdb-row-bot">
    <a href="javascript:void(0)" id="tdb-btn-back" class="tdb-btn tdb-btn-secondary" hidden>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20z"/></svg>
      <span class="tdb-label">RETOUR</span>
    </a>
    <a href="javascript:void(0)" id="tdb-btn-quitretro" class="tdb-btn tdb-btn-warn" hidden>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5V2L8 6l4 4V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>
      <span class="tdb-label">QUITTER RETROVIEW</span>
    </a>
    <a href="javascript:void(0)" id="tdb-btn-defaut" class="tdb-btn" data-navtarget="historique" hidden>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>
      <span class="tdb-label">DEFAUT</span>
    </a>
    <a href="javascript:void(0)" id="tdb-btn-param" class="tdb-btn tdb-admin-only" data-navtarget="configuration" hidden>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19.14 12.94a7.5 7.5 0 0 0 0-1.88l2.03-1.58a.5.5 0 0 0 .12-.63l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.32 7.32 0 0 0-1.63-.95l-.36-2.54a.5.5 0 0 0-.5-.43h-3.84a.5.5 0 0 0-.5.43l-.36 2.54c-.59.24-1.14.56-1.63.95l-2.39-.96a.5.5 0 0 0-.6.22L2.65 8.85a.5.5 0 0 0 .12.63l2.03 1.58a7.5 7.5 0 0 0 0 1.88L2.77 14.52a.5.5 0 0 0-.12.63l1.92 3.32a.5.5 0 0 0 .6.22l2.39-.96c.49.39 1.04.71 1.63.95l.36 2.54a.5.5 0 0 0 .5.43h3.84a.5.5 0 0 0 .5-.43l.36-2.54c.59-.24 1.14-.56 1.63-.95l2.39.96a.5.5 0 0 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.63l-2.03-1.58zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z"/></svg>
      <span class="tdb-label">PARAMETRAGE</span>
    </a>
    <span class="tdb-sep" id="tdb-sep-mid" hidden></span>
    <a href="javascript:void(0)" id="tdb-btn-accueil" class="tdb-btn" data-navtarget="menu">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 3 11h2v9h5v-6h4v6h5v-9h2z"/></svg>
      <span class="tdb-label">ACCUEIL</span>
    </a>
    <a href="javascript:void(0)" id="tdb-btn-profil" class="tdb-btn" data-navtarget="profil">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 12c2.21 0 4-1.79 4-4S14.21 4 12 4 8 5.79 8 8s1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>
      <span class="tdb-label">PROFIL</span>
    </a>
    <a href="javascript:void(0)" id="tdb-btn-comptes" class="tdb-btn tdb-admin-only" data-navtarget="notifications_admin" hidden>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/></svg>
      <span class="tdb-label">COMPTES</span>
    </a>
    <a href="javascript:void(0)" id="tdb-btn-logout" class="tdb-btn tdb-btn-logout">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5-5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z"/></svg>
      <span class="tdb-label">DECONNEXION</span>
    </a>
  </div>
</nav>
<script>
/* ''' + MARKER + ''' */
(function(){
  if (window.__tdbBarBooted) { window.__tdbBarBooted(); return; }

  function tok(){ return localStorage.getItem('jwt_token'); }
  function H(){ return { 'X-Authorization': 'Bearer ' + tok() }; }

  // --- State + entityId resolution ---
  function currentStateId(){
    try {
      var raw = new URL(window.location.href).searchParams.get('state');
      if (!raw) return 'menu';
      var arr = JSON.parse(atob(decodeURIComponent(raw)));
      var last = arr[arr.length - 1];
      return (last && last.id) || 'menu';
    } catch(_) { return 'menu'; }
  }
  function entityIdFromUrl(){
    try {
      var raw = new URL(window.location.href).searchParams.get('state');
      if (!raw) return null;
      var arr = JSON.parse(atob(decodeURIComponent(raw)));
      for (var i = arr.length - 1; i >= 0; i--) {
        var p = arr[i] && arr[i].params;
        if (p && p.entityId && p.entityId.id) return p.entityId.id;
      }
    } catch(_) {}
    return null;
  }

  // --- Visibility rules per state ---
  var VISIBILITY = {
    'menu':              { title:'TDUO chaufferies', crumb:false, ts:false, back:null,        defaut:false, param:false, profil:true,  accueil:false },
    'default':           { title:'TDUO {s}',         crumb:true,  ts:true,  back:null,        defaut:true,  param:true,  profil:true,  accueil:true  },
    'donnees_HP1':       { title:'TDUO {s}',         crumb:true,  ts:true,  back:'default',   defaut:true,  param:true,  profil:true,  accueil:true  },
    'historique':        { title:'TDUO {s}',         crumb:true,  ts:false, back:'default',   defaut:false, param:true,  profil:true,  accueil:true  },
    'fault_diagnostic':  { title:'TDUO {s}',         crumb:true,  ts:false, back:'historique',defaut:false, param:true,  profil:true,  accueil:true  },
    'configuration':     { title:'TDUO {s}',         crumb:true,  ts:false, back:'default',   defaut:true,  param:false, profil:true,  accueil:true  },
    'profil':            { title:'TDUO {s}',         crumb:'Mon profil', ts:false, back:'default', defaut:false, param:false, profil:false, accueil:true },
    'notifications_admin':{ title:'TDUO {s}',        crumb:'Comptes admin', ts:false, back:'default', defaut:false, param:false, profil:true, accueil:true }
  };

  function show(el, yes){ if (!el) return; if (yes) el.removeAttribute('hidden'); else el.setAttribute('hidden',''); }

  function applyState(){
    var sid = currentStateId();
    var v = VISIBILITY[sid] || VISIBILITY['default'];
    var bar = document.getElementById('tdb-bar');
    if (!bar) return false;
    // Title
    var titleText = (typeof v.title === 'string') ? v.title : 'TDUO';
    var serial = window.__tduoInstallName || '';
    var titleEl = document.getElementById('tdb-title-text');
    if (titleEl) titleEl.textContent = titleText.replace('{s}', serial);
    // Breadcrumb separator + residence
    show(document.getElementById('tdb-crumb-sep'), !!v.crumb);
    var resEl = document.getElementById('tdb-residence');
    if (resEl) {
      if (v.crumb === true) {
        resEl.textContent = window.__tduoResidenceName || '';
        show(resEl, true);
      } else if (typeof v.crumb === 'string') {
        resEl.textContent = v.crumb;
        show(resEl, true);
        show(document.getElementById('tdb-crumb-sep'), true);
      } else {
        resEl.textContent = '';
        show(resEl, false);
      }
    }
    // Timestamp
    show(document.getElementById('tdb-laststamp'), !!v.ts);
    // Buttons
    var backBtn = document.getElementById('tdb-btn-back');
    if (backBtn) {
      if (v.back) {
        backBtn.setAttribute('data-navtarget', v.back);
        show(backBtn, true);
      } else {
        show(backBtn, false);
      }
    }
    show(document.getElementById('tdb-btn-defaut'),  v.defaut);
    show(document.getElementById('tdb-btn-param'),   v.param && !!window.__tdbIsAdmin);  // param toujours admin-only
    show(document.getElementById('tdb-btn-profil'),  v.profil);
    show(document.getElementById('tdb-btn-accueil'), v.accueil);
    show(document.getElementById('tdb-btn-comptes'), !!window.__tdbIsAdmin);
    // Quit retroview button : show if sessionStorage.tduo.retroview.endTs is set AND state is donnees_HP1
    var retroEnd = null;
    try { retroEnd = sessionStorage.getItem('tduo.retroview.endTs'); } catch(_) {}
    show(document.getElementById('tdb-btn-quitretro'), !!retroEnd && sid === 'donnees_HP1');
    // Mid separator visible si on a au moins un bouton de nav-pages avant les buttons system
    show(document.getElementById('tdb-sep-mid'), v.defaut || v.param || v.back);
    return true;
  }

  // --- Fetch device + residence + last sample ts ---
  function pad2(n){ return (n < 10 ? '0' : '') + n; }
  function fmtTs(ts){
    var d = new Date(ts);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth()+1) + '/' + (d.getFullYear()%100) + ' a ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }
  function loadDeviceInfo(){
    var eid = entityIdFromUrl();
    if (!eid) { applyState(); return; }
    // Cache si deja en window
    var cached = sessionStorage.getItem('tduo.install.' + eid);
    if (cached) window.__tduoInstallName = cached;
    var cachedRes = sessionStorage.getItem('tduo.residence.' + eid);
    if (cachedRes) window.__tduoResidenceName = cachedRes;
    applyState();  // affichage premier-pass avec cache
    // Fetch frais
    if (!tok()) return;
    Promise.all([
      fetch('/api/device/' + eid, { headers: H() }).then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; }),
      fetch('/api/plugins/telemetry/DEVICE/' + eid + '/values/attributes/SERVER_SCOPE?keys=nom_residence,nom_alternatif',
            { headers: H() }).then(function(r){ return r.ok ? r.json() : []; }).catch(function(){ return []; })
    ]).then(function(arr){
      var dev = arr[0], attrs = arr[1] || [];
      if (dev && dev.name) {
        window.__tduoInstallName = dev.name;
        try { sessionStorage.setItem('tduo.install.' + eid, dev.name); } catch(_) {}
      }
      var byKey = {};
      attrs.forEach(function(a){ byKey[a.key] = a.value; });
      var resName = byKey.nom_residence || byKey.nom_alternatif || (dev && dev.name) || '';
      if (resName) {
        window.__tduoResidenceName = resName;
        try { sessionStorage.setItem('tduo.residence.' + eid, resName); } catch(_) {}
      }
      applyState();
    });
    // Last sample ts
    fetch('/api/plugins/telemetry/DEVICE/' + eid + '/values/timeseries?keys=pac_v2&limit=1',
          { headers: H() }).then(function(r){ return r.ok ? r.json() : null; }).then(function(data){
      var stampEl = document.getElementById('tdb-laststamp');
      if (!stampEl || !data || !data.pac_v2 || !data.pac_v2.length) return;
      var ts = data.pac_v2[0].ts;
      stampEl.textContent = 'Derniere donnee : ' + fmtTs(ts);
      stampEl.classList.toggle('stale', (Date.now() - ts) > 30 * 60 * 1000);
    }).catch(function(){});
  }

  // --- Admin check ---
  function checkAdmin(){
    if (!tok()) { applyState(); return; }
    fetch('/api/auth/user', { headers: H() }).then(function(r){ return r.ok ? r.json() : null; }).then(function(me){
      if (!me) { window.__tdbIsAdmin = false; applyState(); return; }
      if (me.authority === 'TENANT_ADMIN') { window.__tdbIsAdmin = true; applyState(); return; }
      if (me.authority !== 'CUSTOMER_USER') { window.__tdbIsAdmin = false; applyState(); return; }
      fetch('/api/plugins/telemetry/USER/' + me.id.id + '/values/attributes/SERVER_SCOPE?keys=is_admin',
            { headers: H() }).then(function(r){ return r.ok ? r.json() : []; }).then(function(attrs){
        var ok = (attrs || []).some(function(a){ return a.key === 'is_admin' && a.value === true; });
        window.__tdbIsAdmin = ok;
        applyState();
      }).catch(function(){ window.__tdbIsAdmin = false; applyState(); });
    }).catch(function(){ window.__tdbIsAdmin = false; applyState(); });
  }

  // --- Click handlers ---
  function navTo(stateId){
    if (stateId === '__logout__') { doLogout(); return; }
    if (stateId === '__quitretro__') {
      try { sessionStorage.removeItem('tduo.retroview.endTs'); } catch(_) {}
      try { window.dispatchEvent(new CustomEvent('tduo:retroview', { detail: null })); } catch(_) {}
      // reload current state pour rafraichir les widgets
      window.location.reload();
      return;
    }
    var params = {};
    if (stateId !== 'menu') {
      try {
        var raw = new URL(window.location.href).searchParams.get('state');
        if (raw) {
          var arr = JSON.parse(atob(decodeURIComponent(raw)));
          for (var i = arr.length - 1; i >= 0; i--) {
            var p = arr[i] && arr[i].params;
            if (p && p.entityId && p.entityId.id) { params.entityId = p.entityId; break; }
          }
        }
      } catch(_) {}
    }
    var stateB64 = btoa(JSON.stringify([{ id: stateId, params: params }]));
    window.location.assign(window.location.pathname + '?state=' + encodeURIComponent(stateB64));
  }
  function doLogout(){
    try { localStorage.removeItem('jwt_token'); } catch(_) {}
    try { localStorage.removeItem('refresh_token'); } catch(_) {}
    try { sessionStorage.clear(); } catch(_) {}
    (window.top || window).location.href = '/login';
  }
  function wireClicks(){
    var bar = document.getElementById('tdb-bar');
    if (!bar || bar.__tdbWired) return;
    bar.__tdbWired = true;
    bar.addEventListener('click', function(ev){
      var lo = ev.target.closest && ev.target.closest('#tdb-btn-logout');
      if (lo) { ev.preventDefault(); doLogout(); return; }
      var qr = ev.target.closest && ev.target.closest('#tdb-btn-quitretro');
      if (qr) { ev.preventDefault(); navTo('__quitretro__'); return; }
      var nav = ev.target.closest && ev.target.closest('[data-navtarget]');
      if (nav) { ev.preventDefault(); navTo(nav.getAttribute('data-navtarget')); }
    });
  }

  // --- Compact mode + boot ---
  function applyCompact(){
    var bar = document.getElementById('tdb-bar');
    if (!bar) return;
    bar.classList.toggle('tdb-compact', bar.clientWidth < 720);
  }
  function init(){
    var bar = document.getElementById('tdb-bar');
    if (!bar) { setTimeout(init, 100); return; }
    wireClicks();
    checkAdmin();
    loadDeviceInfo();
    applyCompact();
    window.addEventListener('resize', applyCompact);
    window.addEventListener('popstate', function(){ loadDeviceInfo(); applyState(); });
  }
  init();

  window.__tdbBarBooted = function(){ applyState(); loadDeviceInfo(); applyCompact(); };
})();
</script>'''

MERGED_CSS = '''/* ''' + MARKER + ''' : bandeau unifie Topbar+Navbar */
.card { height: 100%; padding: 0; background: transparent; overflow: visible; }
.tdb-bar {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  padding: 8px 18px;
  background: transparent;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  gap: 4px;
}
.tdb-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.tdb-row-top {
  flex: 0 0 auto;
  flex-wrap: nowrap;
}
.tdb-row-bot {
  flex: 0 0 auto;
  flex-wrap: nowrap;
  justify-content: flex-end;
  gap: 6px;
}
.tdb-title {
  flex: 0 0 auto;
  font-size: 18px;
  font-weight: 700;
  color: #222;
  letter-spacing: 0.2px;
  white-space: nowrap;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tdb-title-link, .tdb-title-link:link, .tdb-title-link:visited, .tdb-title-link:hover {
  color: inherit; text-decoration: none; cursor: pointer;
}
.tdb-info {
  display: flex;
  flex-direction: column;
  justify-content: center;
  min-width: 0;
  flex: 1 1 auto;
  gap: 2px;
}
.tdb-breadcrumb {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 18px;
  font-weight: 600;
  color: #c62828;
  min-width: 0;
}
.tdb-crumb-link { color: #c62828; text-decoration: none; cursor: pointer; white-space: nowrap; flex: 0 0 auto; }
.tdb-crumb-link:hover { text-decoration: underline; }
.tdb-crumb-sep { color: #aaa; font-weight: 400; flex: 0 0 auto; }
.tdb-residence { color: #222; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.tdb-laststamp { font-size: 12px; color: #888; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tdb-laststamp.stale { color: #c62828; }
.tdb-sep { flex: 0 0 auto; width: 1px; height: 24px; background: #d0d0d0; margin: 0 6px; }
.tdb-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border-radius: 4px;
  background: #f5f5f5;
  border: 1px solid #d0d0d0;
  color: #444;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.2px;
  text-transform: uppercase;
  text-decoration: none;
  cursor: pointer;
  white-space: nowrap;
  box-sizing: border-box;
  transition: background 0.15s, color 0.15s;
}
.tdb-btn:hover { background: #e0e0e0; color: #222; }
.tdb-btn svg { width: 18px; height: 18px; fill: currentColor; flex: 0 0 auto; }
.tdb-btn.tdb-btn-secondary { background: #fff; }
.tdb-btn.tdb-btn-warn { background: #fff3cd; border-color: #ffeeba; color: #856404; }
.tdb-btn.tdb-btn-warn:hover { background: #ffe5a0; }
.tdb-btn.tdb-btn-logout { padding: 0 10px; background: #fff; }
.tdb-btn.tdb-btn-logout .tdb-label { display: none; }
.tdb-btn[hidden] { display: none !important; }
/* Compact (< 720 px) : labels masques sauf retour */
.tdb-bar.tdb-compact .tdb-btn .tdb-label { display: none; }
.tdb-bar.tdb-compact .tdb-btn { padding: 0 8px; height: 28px; }
.tdb-bar.tdb-compact .tdb-title { font-size: 14px; max-width: 140px; }
.tdb-bar.tdb-compact .tdb-breadcrumb { font-size: 14px; }
.tdb-bar.tdb-compact .tdb-laststamp { display: none; }
.tdb-bar.tdb-compact .tdb-row { gap: 6px; }'''


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    with urllib.request.urlopen(r, timeout=60) as o: return json.loads(o.read().decode('utf-8'))

def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8', 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=300) as o: return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')

def login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    args = ap.parse_args()
    t = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', t)
    print(f'Dashboard v{dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/dashboard/backup/mes-installations.before-merge.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup : {backup}')

    nv = dash['configuration']['widgets'][NAVBAR_ID]
    settings = nv['config']['settings']
    if MARKER in settings.get('cardHtml',''):
        print('  Navbar already merged (idempotent)')
        return
    # Rewrite HTML + CSS de la Navbar
    settings['cardHtml'] = MERGED_HTML
    settings['cardCss']  = MERGED_CSS
    nv['config']['title'] = 'Bandeau unifie'
    # Resize widget : sizeY 2 (au lieu de 1 ou 2 ?) sur main, etc
    print(f'  Navbar HTML/CSS replaced (markers __MERGED_NAVBAR_V1__)')

    # Retirer la Topbar des layouts (mais garder le widget en stash)
    states = dash['configuration']['states']
    topbar_removed = 0
    navbar2btn_removed = 0
    for sid, st in states.items():
        layouts = st.get('layouts', {})
        for lt in ('main', 'mobile'):
            widgets = layouts.get(lt, {}).get('widgets', {}) or {}
            if TOPBAR_ID in widgets:
                del widgets[TOPBAR_ID]
                topbar_removed += 1
            if NAVBAR2BTN_ID in widgets:
                del widgets[NAVBAR2BTN_ID]
                navbar2btn_removed += 1
    print(f'  Removed Topbar from {topbar_removed} layouts, Navbar2btn from {navbar2btn_removed}')

    # S'assurer que la Navbar est presente sur tous les states cibles avec sizeY=2
    for sid in STATES_WITH_NAVBAR:
        st = states.get(sid)
        if not st: continue
        layout = st.setdefault('layouts', {}).setdefault('main', {'widgets': {}, 'gridSettings': {}})
        widgets = layout.setdefault('widgets', {})
        # Decaler les autres widgets si Navbar pas a row=0 yet
        if NAVBAR_ID in widgets:
            widgets[NAVBAR_ID]['row'] = 0
            widgets[NAVBAR_ID]['col'] = 0
            widgets[NAVBAR_ID]['sizeX'] = 24
            widgets[NAVBAR_ID]['sizeY'] = 2
            widgets[NAVBAR_ID]['mobileOrder'] = 0
            widgets[NAVBAR_ID]['mobileHeight'] = 2
        else:
            # Inserer Navbar a row=0 et decaler tout de +2 (sizeY=2)
            for wid, lo in widgets.items():
                lo['row'] = lo.get('row', 0) + 2
                if 'mobileOrder' in lo and lo['mobileOrder'] is not None:
                    lo['mobileOrder'] = lo['mobileOrder'] + 1
            widgets[NAVBAR_ID] = {
                'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 2,
                'mobileOrder': 0, 'mobileHeight': 2,
            }
        print(f'  state {sid}: Navbar at row=0 sizeY=2')

    resp = http_post('/api/dashboard', dash, t)
    print(f'Posted v{resp["version"]}')


if __name__ == '__main__': main()
