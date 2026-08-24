// Logique d'affichage des registres capteurs gaz. SOURCE UNIQUE : ce fichier est
// injecte tel quel dans tsmart.pac_detail_top_wip, tsmart.pac_boiler_info,
// tduo.fault_diagnostic et tsmart.gas_registers. Ne jamais le recopier a la main.
// Regles R1 a R7 : voir docs/superpowers/specs/2026-07-31-registres-capteurs-gaz-dashboard-design.md
(function () {
  var root = (typeof window !== 'undefined') ? window : globalThis;
  if (root.__gasLib) { return; }

  var ERR_BITS = {
    0: 'erreur interne',
    1: 'valeur hors limites',
    3: 'auto-test echoue',
    4: 'module HS (remplacer)',
    5: 'fin de vie atteinte',
    6: 'fin de vie proche'
  };

  function decodeErr(code) {
    var n = Number(code);
    if (code === null || code === undefined || isNaN(n)) { return null; }
    if (n === 0) { return 'OK'; }
    var out = [];
    for (var b = 0; b <= 6; b++) {
      if (n & (1 << b)) { out.push(ERR_BITS[b] || ('bit ' + b)); }
    }
    return out.length ? out.join(' + ') : ('code ' + n);
  }

  function fmtVer(v) {
    var n = Number(v);
    if (v === null || v === undefined || isNaN(n) || n === 0) { return null; }
    return 'v' + (n >> 8) + '.' + (n & 255);
  }

  // R7 : adresse bus nulle ou version 0.0 => le bloc n'a pas ete lu par ce firmware.
  function blockUnread(o) {
    if (!o) { return true; }
    return !(Number(o.addr) > 0) || !(Number(o.fw) > 0);
  }

  function segments(pts, maxGapMs) {
    var gap = maxGapMs || 180000;
    var out = [];
    for (var i = 0; i < pts.length; i++) {
      var ts = pts[i][0], v = pts[i][1];
      var last = out.length ? out[out.length - 1] : null;
      if (last && last.v === v && (ts - last.end) <= gap) { last.end = ts; }
      else { out.push({ v: v, start: ts, end: ts }); }
    }
    return out;
  }

  function row(k, v, cls) {
    return '<div class="pd-kv"><span class="k">' + k + '</span><span class="v' +
           (cls ? ' ' + cls : '') + '">' + v + '</span></div>';
  }

  function rows(sfx, o) {
    if (!o) { return ''; }
    var con = o['con' + sfx];
    if (con === null || con === undefined) { return ''; }          // R3
    var conTxt = (Number(con) * 0.1).toFixed(1) + ' %LFL';
    var err = decodeErr(o['err' + sfx]);
    var errTxt = (err === null) ? '\u2014' : err;

    if (blockUnread({ addr: o['addr' + sfx], fw: o['fwVer' + sfx] })) {   // R7
      return row('Concentration ' + sfx, conTxt) +
             row('Capteur ' + sfx, errTxt + ' \u00b7 registres non lus par ce firmware');
    }

    var thr = o['leakThres' + sfx];
    var ctx = (thr !== null && thr !== undefined && Number(thr) > 0)
      ? '   (seuil ' + (Number(thr) * 0.1).toFixed(1) + ')' : '';      // R4
    var mesure = Number(o['opMode' + sfx]) === 1;
    var leak = Number(o['leak' + sfx]) === 1;

    var out = mesure ? row('Concentration ' + sfx, conTxt + ctx) : '';   // R1
    out += row('\u00c9tat gaz ' + sfx,
               leak ? '\u26a0 ALARME FUITE (maintenue 5 min)' : '\u25cf Aucune alarme',
               leak ? 'v-alarm' : '');                                  // R2
    out += row('Capteur ' + sfx, errTxt +
               (mesure ? ' \u00b7 mesure en cours'
                       : ' \u00b7 d\u00e9marrage \u2014 mesure indisponible'));
    return out;
  }

  root.__gasLib = {
    decodeErr: decodeErr, fmtVer: fmtVer, blockUnread: blockUnread,
    segments: segments, row: row, rows: rows, ERR_BITS: ERR_BITS
  };
})();
