
(function(){
  function tok(){ return localStorage.getItem('jwt_token'); }
  function H(){ return { 'X-Authorization': 'Bearer ' + tok() }; }
  function readEntityIdFromUrl(){
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
  function pad2(n){ return (n < 10 ? '0' : '') + n; }
  function fmtTs(ts){
    var d = new Date(ts);
    return pad2(d.getDate()) + '/' + pad2(d.getMonth() + 1) + '/' + d.getFullYear()
         + ' à ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes());
  }
  function setResidence(name){
    var el = document.getElementById('md-nav-residence');
    if (el && name) el.textContent = name;
    // NB: on stocke la résidence dans une variable SÉPARÉE — ne pas écraser
    // __tduoInstallName (= n° de série device.name) utilisé par la topbar
    // rouge, qui veut afficher "TDUO <serial>" pas "TDUO <résidence>".
    if (name) window.__tduoResidenceName = name;
  }
  function setStamp(ts){
    var el = document.getElementById('md-nav-laststamp');
    if (!el) return;
    if (!ts) { el.textContent = ''; el.classList.remove('stale'); return; }
    el.textContent = 'Dernière donnée : ' + fmtTs(ts);
    // > 30 min → stale (rouge discret)
    el.classList.toggle('stale', (Date.now() - ts) > 30 * 60 * 1000);
  }

  var eid = readEntityIdFromUrl();
  if (!eid) return;
  var barEl0 = document.getElementById('md-nav-default');
  if (barEl0) barEl0.classList.add('md-nav-detail-mode');

  // 1) Résidence : prio nom_residence > nom_alternatif > device.name
  Promise.all([
    fetch('/api/device/' + eid, { headers: H() }).then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; }),
    fetch('/api/plugins/telemetry/DEVICE/' + eid + '/values/attributes/SERVER_SCOPE?keys=nom_residence,nom_alternatif',
          { headers: H() }).then(function(r){ return r.ok ? r.json() : []; }).catch(function(){ return []; }),
  ]).then(function(arr){
    var dev = arr[0], attrs = arr[1] || [];
    var byKey = {};
    attrs.forEach(function(a){ byKey[a.key] = a.value; });
    var name = byKey.nom_residence || byKey.nom_alternatif || (dev && dev.name) || '—';
    setResidence(name);
  });

  // 2) Dernier timestamp — récupère un nom de clé puis la valeur la plus récente.
  fetch('/api/plugins/telemetry/DEVICE/' + eid + '/keys/timeseries', { headers: H() })
    .then(function(r){ return r.ok ? r.json() : []; })
    .then(function(keys){
      if (!keys || !keys.length) return null;
      var k = keys[0];
      return fetch('/api/plugins/telemetry/DEVICE/' + eid + '/values/timeseries?keys=' + encodeURIComponent(k) + '&limit=1',
                   { headers: H() })
        .then(function(r){ return r.ok ? r.json() : null; });
    })
    .then(function(data){
      if (!data) { setStamp(null); return; }
      var maxTs = 0;
      for (var k in data) {
        if (data[k] && data[k][0] && data[k][0].ts > maxTs) maxTs = data[k][0].ts;
      }
      setStamp(maxTs || null);
    })
    .catch(function(){ setStamp(null); });

  // 3) Mode compact si peu d'espace horizontal (≤ 600 px de bandeau).
  function applyCompact(){
    var bar = document.getElementById('md-nav-default');
    if (!bar) return;
    bar.classList.toggle('md-nav-compact', bar.clientWidth < 600);
  }
  applyCompact();
  window.addEventListener('resize', applyCompact);

  // 4) Navigation — scoped uniquement à ce bandeau pour ne pas perturber
  //    les autres delegations (widget markdown PAC-tiles qui écoute aussi
  //    sur document).
  var navEl = document.getElementById('md-nav-default');
  if (navEl && !navEl.__navWired){
    navEl.__navWired = true;
    navEl.addEventListener('click', function(ev){
      var t = ev.target; if (!t || !t.closest) return;
      var nav = t.closest('[data-navtarget]');
      if (!nav) return;
      ev.preventDefault();
      var target = nav.getAttribute('data-navtarget');
      var params = {};
      if (target !== 'menu') {
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
      var stateB64 = btoa(JSON.stringify([{ id: target, params: params }]));
      // Hard navigation pour garantir l'unmount complet des widgets du state precedent
      // (pushState + popstate synthetique laisse parfois les widgets en place)
      window.location.assign(window.location.pathname + '?state=' + encodeURIComponent(stateB64));
    });
  }
})();

