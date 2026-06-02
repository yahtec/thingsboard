#!/usr/bin/env python3
"""
Patch events_history widget :
1) Pour les RESOLUS standalone (apparition hors fenetre), utiliser resolvedTs
   comme appearTs fallback : la colonne APPARITION montre alors la date de
   resolution (mieux que vide).
2) Ajoute une colonne RESOLUTION distincte si resolvedTs est connu.

Idempotent via marker __EVTHIST_RESOL_PATCH__.
"""

import argparse, json, sys, time, urllib.request, urllib.error

WIDGET_ID = 'af86baf0-3fe1-11f1-bbfe-e1395562cba0'
BASE_URL  = 'https://thingsboard.tsmart.fr'
MARKER    = '__EVTHIST_RESOL_PATCH__'

OLD_THEAD = '''<thead><tr>" +
        "        <th>Apparition</th>" +
        "        <th class='col-type'>Type</th>" +
        "        <th>Événement</th>" +
        "        <th class='col-device'>Unité</th>" +
        "        <th class='col-action'>Action</th>" +
        "      </tr></thead>'''

NEW_THEAD = '''<thead><tr>" +
        "        <th>Apparition</th>" +
        "        <th class='col-resol'>Résolution</th>" +
        "        <th class='col-type'>Type</th>" +
        "        <th>Événement</th>" +
        "        <th class='col-device'>Unité</th>" +
        "        <th class='col-action'>Action</th>" +
        "      </tr></thead>'''

OLD_ROW = """self._rowHtml = function(rec) {
    var faultLbl = FAULT_LABELS[rec.fault];
    if (faultLbl === undefined) faultLbl = 'Code ' + rec.fault;
    var devLbl = DEVICE_LABELS[rec.device];
    if (devLbl === undefined) devLbl = (rec.device === 0 ? '' : 'Code ' + rec.device);
    var isActive = (rec.type === 1 && !rec.resolvedTs);
    var cls = isActive ? 'evt-row active' : 'evt-row';
    // Type=4 orphelin : pas d'apparition à afficher.
    var appearTs = rec.appearTs || (rec.type === 4 ? null : rec.ts);
    return '<tr class="' + cls + '">' +
        '<td>' + self._fmtTs(appearTs) + '</td>' +
        '<td class="col-type">' + self._typeChip(rec) + '</td>' +
        '<td>' + (faultLbl || '<span class="evt-muted">—</span>') + '</td>' +
        '<td class="col-device">' + (devLbl || '<span class="evt-muted">—</span>') + '</td>' +
        '<td class="col-action">' + self._actionCell(rec) + '</td>' +
        '</tr>';
};"""

NEW_ROW = """self._rowHtml = function(rec) {
    // """ + MARKER + """ : ajout col Resolution + fallback appearTs sur standalones
    var faultLbl = FAULT_LABELS[rec.fault];
    if (faultLbl === undefined) faultLbl = 'Code ' + rec.fault;
    var devLbl = DEVICE_LABELS[rec.device];
    if (devLbl === undefined) devLbl = (rec.device === 0 ? '' : 'Code ' + rec.device);
    var isActive = (rec.type === 1 && !rec.resolvedTs);
    var cls = isActive ? 'evt-row active' : 'evt-row';
    // Type=4 orphelin sans appearTs : fallback sur resolvedTs (mieux que vide).
    // Le user pourra cliquer pour voir le diagnostic au moment de la resolution.
    var appearTs = rec.appearTs;
    var resolTs  = rec.resolvedTs;
    if (!appearTs && rec.type === 4 && resolTs) {
        appearTs = resolTs;  // fallback : la resolution sert d'ancrage
        rec.appearTs = resolTs;  // utilise par _actionCell aussi
    }
    if (!appearTs && rec.type !== 4) appearTs = rec.ts;
    var apparCell  = self._fmtTs(appearTs);
    var resolCell  = resolTs ? self._fmtTs(resolTs) : '<span class="evt-muted">—</span>';
    return '<tr class="' + cls + '">' +
        '<td>' + apparCell + '</td>' +
        '<td class="col-resol">' + resolCell + '</td>' +
        '<td class="col-type">' + self._typeChip(rec) + '</td>' +
        '<td>' + (faultLbl || '<span class="evt-muted">—</span>') + '</td>' +
        '<td class="col-device">' + (devLbl || '<span class="evt-muted">—</span>') + '</td>' +
        '<td class="col-action">' + self._actionCell(rec) + '</td>' +
        '</tr>';
};"""

# Aussi : la cellule vide quand pas d'events doit avoir colspan="6" (au lieu de 5)
OLD_EMPTY = '<tr><td colspan="5" class="evt-empty">Aucun événement</td></tr>'
NEW_EMPTY = '<tr><td colspan="6" class="evt-empty">Aucun événement</td></tr>'


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
    w = http_get(f'/api/widgetType/{WIDGET_ID}', t)
    print(f'Widget: {w["name"]} v{w.get("version","?")}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    with open(f'scripts/tb/backup/widgets-tduo-v1/events_history.before_resol.{ts}.json','wb') as f:
        f.write(json.dumps(w, ensure_ascii=False, indent=2).encode('utf-8'))
    cs = w['descriptor']['controllerScript']
    if MARKER in cs:
        print('  Already patched (idempotent skip)')
        return
    # Patches
    if OLD_THEAD not in cs: sys.exit('OLD_THEAD pattern not found')
    if OLD_ROW   not in cs: sys.exit('OLD_ROW pattern not found')
    if OLD_EMPTY not in cs: sys.exit('OLD_EMPTY pattern not found')
    new_cs = cs.replace(OLD_THEAD, NEW_THEAD, 1)
    new_cs = new_cs.replace(OLD_ROW,   NEW_ROW,   1)
    new_cs = new_cs.replace(OLD_EMPTY, NEW_EMPTY, 1)
    w['descriptor']['controllerScript'] = new_cs
    # Add CSS rule for col-resol (after col-type or similar)
    css = w['descriptor'].get('templateCss', '') or ''
    if '.col-resol' not in css:
        css = css.rstrip() + '\n/* ' + MARKER + ' */\n.col-resol { white-space: nowrap; }\n'
        w['descriptor']['templateCss'] = css
    print(f'  controllerScript: {len(cs)} -> {len(new_cs)} chars')
    resp = http_post('/api/widgetType', w, t)
    print(f'Posted OK. New version: {resp.get("version","?")}')


if __name__ == '__main__': main()
