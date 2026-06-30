self.onInit = function(){};
self.onDataUpdated = function(){
  var $c = self.ctx.$container;
  var host = $c.find('.gz-host');
  if (!host.length) return;

  // Lire les settings du widget pour savoir si c'est HP ou BP
  var settings = self.ctx.settings || {};
  var col = settings.gaugeType || 'hp'; // 'hp' ou 'bp'

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

  function gauge(val, min, max, col){
    var cx = 100, cy = 100, R = 85, nn = 10;
    function pt(t, r){
      var a = (135 + t * 270) * Math.PI / 180;
      return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    }
    var f = parseFloat(val);
    var t = isNaN(f) ? 0 : (f - min) / (max - min);
    if (t < 0) t = 0; if (t > 1) t = 1;

    var g = '';
    for (var i = 0; i <= nn; i++){
      var tt = i / nn;
      var p1 = pt(tt, R), p2 = pt(tt, R - 10), pl = pt(tt, R - 22);
      g += '<line x1="' + p1[0].toFixed(1) + '" y1="' + p1[1].toFixed(1) +
           '" x2="' + p2[0].toFixed(1) + '" y2="' + p2[1].toFixed(1) +
           '" stroke="#aaa" stroke-width="1.5"/>';
      g += '<text x="' + pl[0].toFixed(1) + '" y="' + (pl[1] + 3).toFixed(1) +
           '" font-size="10" fill="#777" text-anchor="middle">' +
           Math.round(min + (max - min) * tt) + '</text>';
    }

    var tip = pt(t, R - 6), tail = pt(t, -16);
    var c  = col === 'hp' ? '#c62828' : '#1976d2';
    var bg = col === 'hp' ? '#ffebee' : '#e3f2fd';

    return '<svg viewBox="0 0 200 200" class="gz-svg">' +
      '<circle cx="100" cy="100" r="90" fill="' + bg + '" stroke="#ececec" stroke-width="1.5"/>' +
      g +
      '<line x1="' + tail[0].toFixed(1) + '" y1="' + tail[1].toFixed(1) +
      '" x2="' + tip[0].toFixed(1) + '" y2="' + tip[1].toFixed(1) +
      '" stroke="' + c + '" stroke-width="2.5" stroke-linecap="round"/>' +
      '<circle cx="100" cy="100" r="7" fill="#333"/>' +
      '<text x="100" y="140" font-size="12" fill="#9e9e9e" text-anchor="middle">bar</text>' +
      '</svg>';
  }

  var X = getHP(), n = X.n, H = X.H;
  var hp = H.HP || {}, inv = H.invert || {};

  // Config selon HP ou BP
  var cfg = {
    hp: { title: 'Pression HP', val: hp.pHi, min: -5, max: 35,
          lcdColor: '#ff3b30', tempLabel: 'T COND', tempVal: hp.tCond },
    bp: { title: 'Pression BP', val: hp.pLo, min: -5, max: 25,
          lcdColor: '#29b6f6', tempLabel: 'T EVAP', tempVal: hp.tEvap }
  };
  var c = cfg[col] || cfg.hp;

  var lcdColorClass = col === 'bp' ? ' bp' : '';

  var html =
    '<div class="gz-card' + lcdColorClass + '">' +
      '<div class="gz-title">' + c.title + '</div>' +
      gauge(c.val, c.min, c.max, col) +
      '<div class="gz-lcd">' +
        '<span class="gz-lcd-val">' + fv(c.val, 1) + '</span>' +
      '</div>' +
      '<div class="gz-sep"></div>' +
      '<div class="gz-temp-box">' +
        '<div class="gz-temp-label">' + c.tempLabel + '</div>' +
        '<div class="gz-temp-value">' + fv(c.tempVal, 1) + ' °C</div>' +
      '</div>' +
    '</div>';

  host.html(html);
};

self.typeParameters = function(){
  return { maxDatasources: 1, maxDataKeys: 2, singleEntity: true };
};
self.onResize = function(){};
self.onDestroy = function(){};
