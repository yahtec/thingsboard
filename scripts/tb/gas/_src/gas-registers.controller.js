// Widget timeline des registres capteurs gaz. Une piste par registre, en escalier,
// SANS lissage — contrairement au graphe de courbes, qui moyenne sur +-3 points.
//
// Se branche sur le singleton window.__pacData cree par tsmart.pac_chart : meme
// requete pac_v2, donc meme periode et meme zoom que les courbes, sans requete
// supplementaire. Le bloc PD() ci-dessous est le MEME bootstrap que celui du type
// tsmart.pac_chart : il doit rester compatible avec la forme de `hist`
// ([[ts, payload], ...]). Toute divergence casserait la synchronisation.
self.onInit = function () {
  function PD() {
    if (window.__pacData) return window.__pacData;
    var d = {
      hours: 12, frac: 1, offset: 0, hist: [], eid: null, et: 'DEVICE', ls: [], fetching: false,
      register: function (fn) { if (this.ls.indexOf(fn) < 0) this.ls.push(fn); },
      unregister: function (fn) { var i = this.ls.indexOf(fn); if (i >= 0) this.ls.splice(i, 1); },
      notify: function () { this.ls.forEach(function (fn) { try { fn(); } catch (e) {} }); },
      ensure: function (et, eid) {
        if (!eid) return;
        if (eid !== this.eid) { this.eid = eid; this.et = et || 'DEVICE'; this.load(); }
        else if (this.hist.length) { this.notify(); }
        else if (!this.fetching) { this.load(); }
      },
      setHours: function (h) { this.hours = h; this.frac = 1; this.offset = 0; this.load(); },
      setFrac: function (f) { this.frac = f; this.notify(); },
      setOffset: function (o) { this.offset = o; this.notify(); },
      load: function () {
        var s = this; if (!s.eid) return;
        s.fetching = true;
        var end = Date.now(), start = end - s.hours * 3600000;
        fetch('/api/plugins/telemetry/' + s.et + '/' + s.eid +
              '/values/timeseries?keys=pac_v2&startTs=' + start + '&endTs=' + end +
              '&limit=8000&orderBy=ASC',
              { headers: { 'X-Authorization': 'Bearer ' + localStorage.getItem('jwt_token') } })
          .then(function (r) { return r.json(); })
          .then(function (dd) {
            var arr = (dd && dd.pac_v2) || [];
            s.hist = arr.map(function (x) {
              var v = null; try { v = JSON.parse(x.value); } catch (e) {}
              return [Number(x.ts), v];
            }).filter(function (x) { return x[1]; });
            s.fetching = false; s.notify();
          })
          .catch(function () { s.fetching = false; s.notify(); });
      }
    };
    window.__pacData = d; return d;
  }

  function stateParams() {
    try {
      var raw = new URL(window.location.href).searchParams.get('state');
      if (!raw) { return {}; }
      var arr = JSON.parse(atob(decodeURIComponent(raw)));
      for (var i = arr.length - 1; i >= 0; i--) { if (arr[i] && arr[i].params) { return arr[i].params; } }
    } catch (e) {}
    return {};
  }

  var GEO = { mL: 150, mR: 12, mT: 6, mB: 20, lane: 22, gapLane: 6 };

  // Meme echappement que les deux sites SVG existants (label de piste, texte de
  // segment) : ces valeurs viennent de la configuration (def.label, def.map[v].t)
  // et sont injectees dans du HTML (SVG ou tooltip), donc jamais telles quelles.
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }

  self._draw = function () {
    var $c = self.ctx.$container;
    if (!$c.find('.gr-card').length) { return; }
    var s = self.ctx.settings || {};
    $c.find('.gr-title').text(s.title || 'Registres gaz');
    var defs = s.lanes || [];
    var n = parseInt(stateParams().hpIndex || stateParams().hp || 1) || 1;
    var hist = (window.__pacData && window.__pacData.hist) || [];

    // Meme fenetre de zoom que les courbes : on rejoue frac/offset du singleton.
    var view = hist;
    if (hist.length) {
      var tA = hist[hist.length - 1][0], tB = hist[0][0], span = tA - tB;
      var fr = (window.__pacData && window.__pacData.frac) || 1;
      var off = (window.__pacData && window.__pacData.offset) || 0;
      var vEnd = tA - off * span, vStart = vEnd - fr * span;
      view = hist.filter(function (p) { return p[0] >= vStart && p[0] <= vEnd; });
    }

    var lanes = window.__gasLib.buildLanes(view, defs, n);
    var svgEl = $c.find('.gr-svg')[0];
    if (!lanes.length) {
      svgEl.innerHTML = '<div class="gr-empty">Pas de registre sur la periode</div>';
      // Le survol lit plot._cd (pas svgEl._cd) : c'est cette cible qu'il faut vider,
      // sinon une navigation vers une installation sans registre garde le tooltip
      // de l'installation precedente.
      var plotEl = $c.find('.gr-plot')[0];
      if (plotEl) { plotEl._cd = null; }
      return;
    }

    var W = $c.find('.gr-plot')[0].clientWidth || 600;
    var H = GEO.mT + GEO.mB + lanes.length * (GEO.lane + GEO.gapLane);
    var tmin = Infinity, tmax = -Infinity;
    lanes.forEach(function (l) {
      l.segs.forEach(function (g) {
        if (g.start < tmin) { tmin = g.start; }
        if (g.end > tmax) { tmax = g.end; }
      });
    });
    if (tmax === tmin) { tmax = tmin + 60000; }
    function X(t) { return GEO.mL + (t - tmin) / (tmax - tmin) * (W - GEO.mL - GEO.mR); }

    var svg = '<svg width="' + W + '" height="' + H + '" viewBox="0 0 ' + W + ' ' + H + '">';
    lanes.forEach(function (l, li) {
      var y = GEO.mT + li * (GEO.lane + GEO.gapLane);
      svg += '<text x="0" y="' + (y + GEO.lane * 0.7) + '" font-size="11">' +
             esc(l.label) + '</text>';
      l.segs.forEach(function (g) {
        var x1 = X(g.start), x2 = Math.max(X(g.end), x1 + 2);
        svg += '<rect x="' + x1.toFixed(1) + '" y="' + y + '" width="' + (x2 - x1).toFixed(1) +
               '" height="' + GEO.lane + '" fill="' + g.color + '" rx="2"/>';
        if ((x2 - x1) > 44) {
          svg += '<text x="' + (x1 + 5).toFixed(1) + '" y="' + (y + GEO.lane * 0.7) +
                 '" font-size="10" fill="#fff">' +
                 esc(g.txt) + '</text>';
        }
      });
    });
    for (var q = 0; q <= 4; q++) {
      var tq = tmin + (tmax - tmin) * q / 4, dq = new Date(tq);
      svg += '<text x="' + X(tq).toFixed(1) + '" y="' + (H - 6) +
             '" font-size="10" text-anchor="middle">' +
             ('0' + dq.getHours()).slice(-2) + ':' + ('0' + dq.getMinutes()).slice(-2) + '</text>';
    }
    svg += '</svg>';
    svgEl.innerHTML = svg;

    // Survol : la duree d'un segment est l'information la plus utile de ce widget
    // (elle permet par exemple de verifier la tenue de 5 min d'une alarme).
    var plot = $c.find('.gr-plot')[0], tip = $c.find('.gr-tip')[0];
    plot._cd = { lanes: lanes, tmin: tmin, tmax: tmax, W: W };
    if (!plot._bound) {
      plot._bound = true;
      plot.addEventListener('mousemove', function (ev) {
        var cd = plot._cd;
        if (!cd) { return; }
        var r = plot.getBoundingClientRect();
        var x = ev.clientX - r.left, y = ev.clientY - r.top;
        var li = Math.floor((y - GEO.mT) / (GEO.lane + GEO.gapLane));
        if (li < 0 || li >= cd.lanes.length) { tip.style.display = 'none'; return; }
        var t = cd.tmin + (x - GEO.mL) / ((cd.W - GEO.mL - GEO.mR) || 1) * (cd.tmax - cd.tmin);
        var segs = cd.lanes[li].segs, seg = null;
        for (var i = 0; i < segs.length; i++) {
          if (t >= segs[i].start && t <= segs[i].end) { seg = segs[i]; break; }
        }
        if (!seg) { tip.style.display = 'none'; return; }
        function hm(ts) {
          var d = new Date(ts);
          return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
        }
        var mn = Math.max(1, Math.round((seg.end - seg.start) / 60000));
        tip.innerHTML = esc(cd.lanes[li].label) + ' — <b>' + esc(seg.txt) + '</b><br>de ' +
                        hm(seg.start) + ' à ' + hm(seg.end) + ' (' + mn + ' min)';
        tip.style.display = 'block';
        tip.style.left = Math.max(4, Math.min(x + 12, cd.W - 230)) + 'px';
        tip.style.top = (GEO.mT + li * (GEO.lane + GEO.gapLane) + GEO.lane + 4) + 'px';
      });
      plot.addEventListener('mouseleave', function () { tip.style.display = 'none'; });
    }
  };

  PD().register(self._draw);
};
self.onDataUpdated = function () {
  var ds = self.ctx.datasources && self.ctx.datasources[0];
  if (ds && ds.entityId && window.__pacData) {
    window.__pacData.ensure(ds.entityType || 'DEVICE', ds.entityId);
  }
  if (self._draw) { self._draw(); }
};
self.onResize = function () { if (self._draw) { self._draw(); } };
self.onDestroy = function () {
  if (window.__pacData && self._draw) { window.__pacData.unregister(self._draw); }
};
self.typeParameters = function () {
  return { maxDatasources: 1, maxDataKeys: 2, singleEntity: true };
};
