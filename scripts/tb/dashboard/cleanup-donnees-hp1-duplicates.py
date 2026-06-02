#!/usr/bin/env python3
"""
Nettoyage des doublons sur le state donnees_HP1 apres deploiement du
bandeau unifie :

1) Patch PAC Info widget : retire les boutons Accueil + Retour du header
   (mon Navbar les a deja). PRESERVE le bouton Retroview (declencheur picker).

2) Retire du layout donnees_HP1 :
   - Action button (c2ed2cfc...) - 'Retour' widget redondant
   - HTML Card placeholder vide (153fe8c0...)

3) Shift les widgets restants pour combler row=2 (sous Navbar sizeY=2) :
   - PAC Info row=3 -> row=2
   - Timeline row=10 -> row=9
   - PAC Chart row=11.5 -> row=10.5
   - Chaudiere Info row=19.5 -> row=18.5
   - Chaudiere Chart row=25.5 -> row=24.5
   - Repartition row=33.5 -> row=32.5

Idempotent (verifie markers).
"""

import argparse, json, sys, time, urllib.request, urllib.error, re

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
PAC_INFO_ID  = '49e69aac-15bc-32c4-c32d-c474cfeffa82'
ACTION_BTN_ID = 'c2ed2cfc-40af-8418-01c4-ca46a634e6b4'
HTML_CARD_ID = '153fe8c0-a100-2d15-b20b-b2dcdb7b58a5'
BASE_URL     = 'https://thingsboard.tsmart.fr'
MARKER       = '__PACINFO_NAV_BTNS_REMOVED_V1__'


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


def patch_pac_info(dash):
    """Retire les boutons Accueil + Retour du markdownTextFunction."""
    pi = dash['configuration']['widgets'].get(PAC_INFO_ID)
    if not pi: return False, 'PAC Info widget not found'
    md = pi['config']['settings'].get('markdownTextFunction', '')
    if MARKER in md:
        return False, 'already patched (idempotent)'
    # Lines a retirer (avec leur full context exact)
    lines_to_remove = [
        # Bouton Accueil - une ligne complete avec icone SVG
        "html += '<a href=\"#\" id=\"nav-home-btn\" class=\"back-btn\"><svg class=\"nav-svg-icon\" viewBox=\"0 0 24 24\" aria-hidden=\"true\"><path fill=\"currentColor\" d=\"M12 3 3 11h2v9h5v-6h4v6h5v-9h2z\"/></svg><span class=\"back-label\">Accueil</span></a>';",
        # Bouton Retour - une ligne complete
        "html += '<a href=\"#\" id=\"nav-back-btn\" class=\"back-btn\"><span class=\"back-icon\">&#8592;</span><span class=\"back-label\">Retour</span></a>';",
    ]
    md_new = md
    removed = 0
    for line in lines_to_remove:
        if line in md_new:
            md_new = md_new.replace(line, '// ' + MARKER + ' : ' + line.split('"back-label">')[1].split('</span>')[0] + ' removed (now in unified navbar)', 1)
            removed += 1
    if removed == 0:
        return False, 'no matching lines found (PAC Info code may have changed)'
    # Add marker comment to track patch
    if MARKER not in md_new:
        md_new = '// ' + MARKER + '\n' + md_new
    pi['config']['settings']['markdownTextFunction'] = md_new
    return True, f'removed {removed} button lines'


def patch_layout(dash):
    """Cleanup donnees_HP1 layout : remove Action button + HTML Card, shift remaining widgets."""
    st = dash['configuration']['states'].get('donnees_HP1')
    if not st: return False, 'donnees_HP1 state not found'
    widgets = st['layouts']['main']['widgets']
    removed = []
    for wid in (ACTION_BTN_ID, HTML_CARD_ID):
        if wid in widgets:
            del widgets[wid]
            removed.append(wid[:8])
    # Shift restant : row=3->2, row=10->9, row=11.5->10.5, row=19.5->18.5, row=25.5->24.5, row=33.5->32.5
    shifts = {3: 2, 10: 9, 11.5: 10.5, 19.5: 18.5, 25.5: 24.5, 33.5: 32.5}
    shifted = 0
    for wid, lo in widgets.items():
        r = lo.get('row')
        if r in shifts:
            lo['row'] = shifts[r]
            shifted += 1
    return True, f'removed {len(removed)} widgets, shifted {shifted}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    args = ap.parse_args()
    t = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', t)
    print(f'Dashboard v{dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    with open(f'scripts/tb/dashboard/backup/mes-installations.cleanup-hp1.{ts}.json','wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    pc, pmsg = patch_pac_info(dash)
    print(f'  PAC Info : {pmsg}')
    lc, lmsg = patch_layout(dash)
    print(f'  Layout   : {lmsg}')

    if not pc and not lc:
        print('Nothing to do')
        return
    resp = http_post('/api/dashboard', dash, t)
    print(f'Posted v{resp["version"]}')


if __name__ == '__main__': main()
