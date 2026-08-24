// Tests node de gas_lib.js. Lancement : node gas_lib.test.js
// Le fichier testé s'installe sur `window` ; on le simule avant evaluation.
const fs = require('fs');
const path = require('path');
const assert = require('assert');

global.window = {};
new Function(fs.readFileSync(path.join(__dirname, 'gas_lib.js'), 'utf8'))();
const G = global.window.__gasLib;

let ok = 0;
function t(name, fn) {
  try { fn(); ok++; console.log('  ok   ' + name); }
  catch (e) { console.error('  FAIL ' + name + ' : ' + e.message); process.exitCode = 1; }
}

t('decodeErr(0) vaut OK', () => assert.strictEqual(G.decodeErr(0), 'OK'));
t('decodeErr(16) isole le bit 4', () =>
  assert.strictEqual(G.decodeErr(16), 'module HS (remplacer)'));
t('decodeErr(18) combine les bits 1 et 4', () =>
  assert.strictEqual(G.decodeErr(18), 'valeur hors limites + module HS (remplacer)'));
t('decodeErr(null) vaut null', () => assert.strictEqual(G.decodeErr(null), null));
t('decodeErr(4) nomme le bit reserve', () =>
  assert.strictEqual(G.decodeErr(4), 'bit 2'));

t('fmtVer(256) vaut v1.0', () => assert.strictEqual(G.fmtVer(256), 'v1.0'));
t('fmtVer(257) vaut v1.1', () => assert.strictEqual(G.fmtVer(257), 'v1.1'));
t('fmtVer(0) vaut null car une version 0.0 n existe pas', () =>
  assert.strictEqual(G.fmtVer(0), null));

t('blockUnread detecte le bloc non lu (R7)', () =>
  assert.strictEqual(G.blockUnread({ addr: 0, fw: 0 }), true));
t('blockUnread accepte un bloc renseigne', () =>
  assert.strictEqual(G.blockUnread({ addr: 4, fw: 256 }), false));
t('blockUnread refuse une adresse nulle meme avec version', () =>
  assert.strictEqual(G.blockUnread({ addr: 0, fw: 256 }), true));
t('blockUnread accepte un bloc lu dont la version est illisible', () =>
  assert.strictEqual(G.blockUnread({ addr: 4, fw: 0 }), false));

t('segments fusionne les valeurs identiques consecutives', () => {
  const s = G.segments([[0, 0], [60000, 0], [120000, 1]], 180000);
  assert.strictEqual(s.length, 2);
  assert.deepStrictEqual([s[0].v, s[0].start, s[0].end], [0, 0, 60000]);
  assert.strictEqual(s[1].v, 1);
});
t('segments coupe sur un trou de donnees', () => {
  const s = G.segments([[0, 1], [60000, 1], [600000, 1]], 180000);
  assert.strictEqual(s.length, 2, 'le trou de 9 min doit couper le segment');
});
t('segments tolere une entree vide', () =>
  assert.deepStrictEqual(G.segments([], 180000), []));

// rows() : R1, R2, R3, R4, R7
const PLEIN = { conR290: 14, errR290: 0, leakR290: 0, leakThresR290: 100,
                opModeR290: 1, addrR290: 4, fwVerR290: 256 };
t('rows affiche la concentration avec le seuil en contexte (R4)', () => {
  const h = G.rows('R290', PLEIN);
  assert.ok(h.includes('1.4 %LFL'), 'concentration attendue');
  assert.ok(h.includes('(seuil 10.0)'), 'seuil attendu en contexte');
});
t('rows annonce l absence d alarme', () =>
  assert.ok(G.rows('R290', PLEIN).includes('Aucune alarme')));
t('rows signale l alarme et sa tenue de 5 min (R2)', () => {
  const h = G.rows('R290', Object.assign({}, PLEIN, { leakR290: 1, conR290: 123 }));
  assert.ok(h.includes('ALARME FUITE'), 'libelle d alarme attendu');
  assert.ok(h.includes('5 min'), 'mention du maintien attendue');
  assert.ok(h.includes('v-alarm'), 'classe CSS d alarme attendue');
});
t('rows masque la concentration hors mode mesure (R1)', () => {
  const h = G.rows('R290', Object.assign({}, PLEIN, { opModeR290: 0 }));
  assert.ok(!h.includes('%LFL'), 'aucune concentration ne doit etre affichee');
  assert.ok(h.includes('mesure indisponible'));
});
t('rows masque seuil et mode quand le bloc n est pas lu (R7)', () => {
  const h = G.rows('R290', { conR290: 28, errR290: 0, leakR290: 0,
                             leakThresR290: 0, opModeR290: 0, addrR290: 0, fwVerR290: 0 });
  assert.ok(h.includes('2.8 %LFL'), 'la concentration reste valide');
  assert.ok(!h.includes('seuil'), 'aucun seuil ne doit etre affiche');
  assert.ok(!h.includes('Aucune alarme'), 'aucun etat d alarme ne doit etre affiche');
  assert.ok(h.includes('registres non lus par ce firmware'));
});
t('rows ne rend rien sans concentration (R3)', () =>
  assert.strictEqual(G.rows('G20', { conG20: null }), ''));
t('rows fonctionne a l identique sur le suffixe G20', () => {
  const h = G.rows('G20', { conG20: 40, errG20: 16, leakG20: 0, leakThresG20: 100,
                            opModeG20: 1, addrG20: 5, fwVerG20: 256 });
  assert.ok(h.includes('4.0 %LFL'));
  assert.ok(h.includes('module HS (remplacer)'), 'le decodage des bits doit s appliquer');
});

console.log(ok + ' assertions passees');
