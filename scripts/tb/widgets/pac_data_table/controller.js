self.onInit = function(){};
self.onDataUpdated = function(){
  var $c = self.ctx.$container;
  var host = $c.find('.pdt-host');
  if (!host.length) return;

  function stateParams(){
    try {
      var raw = new URL(window.location.href).searchParams.get('state');
      if (!raw) return {};
      var arr = JSON.parse(atob(decodeURIComponent(raw)));
      for (var i = arr.length - 1; i >= 0; i--){
        if (arr[i] && arr[i].params) return arr[i].params;
      }
    } catch(e){}
    return {};
  }

  function fv(v, dec){
    if (v == null || v === '') return '—';
    var f = parseFloat(v);
    if (isNaN(f)) return '—';
    return f.toFixed(dec == null ? 1 : dec);
  }

  function htime(v){ var f = parseFloat(v); return isNaN(f) ? null : f / 3600; }

  function kv(label, val, unit, dec){
    return '<div class="pdt-row">' +
      '<span class="pdt-label">' + label + '</span>' +
      '<span class="pdt-value">' + fv(val, dec) +
        (unit ? '<span class="pdt-unit">' + unit + '</span>' : '') +
      '</span>' +
    '</div>';
  }

  function getHP(){
    var raw = null;
    (self.ctx.data || []).forEach(function(d){
      if (d.dataKey && /pac_v2/i.test(d.dataKey.name) && d.data && d.data.length)
        raw = d.data[d.data.length - 1][1];
    });
    var p = null;
    if (raw){ try { p = (typeof raw === 'string') ? JSON.parse(raw) : raw; } catch(e){} }
    var n = parseInt(stateParams().hpIndex || stateParams().hp || 1) || 1;
    return { n: n, H: (p && p.HPs && p.HPs[n - 1]) || {} };
  }

  var X = getHP(), n = X.n, H = X.H;
  var hp = H.HP || {}, inv = H.invert || {};

  var html =
    '<div class="pdt-card">' +
      '<div class="pdt-card-title">Données PAC ' + n + '</div>' +
      '<div class="pdt-rows">' +
        kv('Fréquence compresseur', inv.freq, ' Hz', 1) +
        kv('Puissance compresseur', inv.pwr, ' W', 0) +
        kv('Vitesse ventilateur', hp.rpm, ' rpm', 0) +
        kv('Position détendeur', hp.dpf, '', 0) +
        kv('T° surchauffe', hp.tOH, ' °C', 1) +
        kv('Temps de fonctionnement', htime(hp.time), ' h', 0) +
      '</div>' +
    '</div>';

  host.html(html);
};

self.typeParameters = function(){
  return { maxDatasources: 1, maxDataKeys: 2, singleEntity: true };
};
self.onResize = function(){};
self.onDestroy = function(){};
