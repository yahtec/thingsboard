// Tests node du calcul des pistes. Lancement : node gas_lanes.test.js
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

// `hist` a la forme produite par le singleton pac_v2 : [[ts, payload], ...]
function hist(vals, champ) {
  return vals.map(function (v, i) {
    const hp = {}; hp[champ] = v;
    return [i * 60000, { HPs: [{ HP: hp, boil: {} }] }];
  });
}

const LANE_LEAK = {
  field: 'HP.leakR290', label: 'Alarme fuite R290',
  map: { 0: { t: 'non', c: '#e8f5e9' }, 1: { t: 'ALARME', c: '#e53935' } }
};

t('getField resout un chemin pointe dans le slot demande', () => {
  const p = { HPs: [{ HP: { conR290: 14 } }, { HP: { conR290: 99 } }] };
  assert.strictEqual(G.getField(p, 'HP.conR290', 1), 14);
  assert.strictEqual(G.getField(p, 'HP.conR290', 2), 99);
});
t('getField tolere un slot absent', () => {
  assert.strictEqual(G.getField({ HPs: [] }, 'HP.conR290', 1), undefined);
});

t('buildLanes traduit les valeurs par la table map', () => {
  const l = G.buildLanes(hist([0, 0, 1, 1, 0], 'leakR290'), [LANE_LEAK], 1);
  assert.strictEqual(l.length, 1);
  assert.strictEqual(l[0].label, 'Alarme fuite R290');
  assert.deepStrictEqual(l[0].segs.map(s => s.txt), ['non', 'ALARME', 'non']);
  assert.strictEqual(l[0].segs[1].color, '#e53935');
});
t('buildLanes conserve les bornes temporelles des segments', () => {
  const l = G.buildLanes(hist([0, 0, 1], 'leakR290'), [LANE_LEAK], 1);
  assert.strictEqual(l[0].segs[0].start, 0);
  assert.strictEqual(l[0].segs[0].end, 60000);
  assert.strictEqual(l[0].segs[1].start, 120000);
});
t('buildLanes omet une piste sans donnee (R3)', () => {
  const l = G.buildLanes(hist([0, 1], 'leakR290'),
    [LANE_LEAK, { field: 'boil.leakG20', label: 'Alarme fuite G20', map: {} }], 1);
  assert.strictEqual(l.length, 1, 'la piste G20 sans donnee ne doit pas etre dessinee');
});
t('buildLanes decode les champs de bits', () => {
  const l = G.buildLanes(hist([0, 16], 'errR290'),
    [{ field: 'HP.errR290', label: 'Defauts capteur R290', kind: 'errbits' }], 1);
  assert.deepStrictEqual(l[0].segs.map(s => s.txt), ['OK', 'module HS (remplacer)']);
});
t('buildLanes met en evidence un champ de bits non nul', () => {
  const l = G.buildLanes(hist([16], 'errR290'),
    [{ field: 'HP.errR290', label: 'Defauts', kind: 'errbits' }], 1);
  assert.strictEqual(l[0].segs[0].color, '#e53935');
});
t('buildLanes met en forme les pistes de valeur avec echelle et unite', () => {
  const l = G.buildLanes(hist([100, 100], 'leakThresR290'),
    [{ field: 'HP.leakThresR290', label: 'Seuil R290', kind: 'value',
       scale: 0.1, unit: '%LFL', d: 1 }], 1);
  assert.strictEqual(l[0].segs.length, 1, 'une valeur constante = un seul segment');
  assert.strictEqual(l[0].segs[0].txt, '10.0 %LFL');
});
t('buildLanes change de teinte a chaque changement de valeur', () => {
  const l = G.buildLanes(hist([4, 4, 5], 'addrR290'),
    [{ field: 'HP.addrR290', label: 'Adresse bus R290', kind: 'value' }], 1);
  assert.strictEqual(l[0].segs.length, 2);
  assert.notStrictEqual(l[0].segs[0].color, l[0].segs[1].color,
    'un changement de valeur doit etre visible');
});
t('buildLanes ignore les echantillons nuls', () => {
  const h = hist([0, null, 0], 'leakR290');
  const l = G.buildLanes(h, [LANE_LEAK], 1);
  assert.strictEqual(l[0].segs.length, 1);
});
t('buildLanes nomme les valeurs hors table', () => {
  const l = G.buildLanes(hist([7], 'leakR290'), [LANE_LEAK], 1);
  assert.strictEqual(l[0].segs[0].txt, '7');
});

console.log(ok + ' assertions passees');
