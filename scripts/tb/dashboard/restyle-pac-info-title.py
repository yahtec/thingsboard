#!/usr/bin/env python3
"""
Restyle le bandeau titre du widget PAC Info (donnees_HP1 state) :
- "Donnees PAC N" -> "PAC HYBRIDE N{N}"
- Style frame-title (h2) -> bloc-title rouge uppercase letter-spaced
  (meme look que les bloc-title de chaque PAC dans le big widget unite_backup)

Idempotent via marker.

Usage:
  restyle-pac-info-title.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'
PAC_INFO_ID  = '49e69aac-15bc-32c4-c32d-c474cfeffa82'
MARKER       = '__PAC_INFO_TITLE_RESTYLED__'

OLD_HTML = "html += '<h2 class=\"frame-title\">Données PAC '+idx+'</h2>';"
NEW_HTML = "html += '<h2 class=\"pac-hybride-title\">PAC Hybride n'+idx+'</h2>'; // " + MARKER

# CSS to inject (block-title styling from unite_backup)
CSS_ADD = f'''
/* {MARKER} */
.tb-markdown-view .pac-hybride-title {{
    font-size: 14px;
    font-weight: 700;
    color: #c62828;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0 0 6px;
    padding: 0 0 6px;
    border-bottom: 1px solid #f0f0f0;
}}
'''


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

    token = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Version: {dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/dashboard/backup/mes-installations.title.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))

    w = dash['configuration']['widgets'].get(PAC_INFO_ID)
    if not w: sys.exit('PAC Info widget not found')
    md = w['config']['settings'].get('markdownTextFunction', '')
    css = w['config']['settings'].get('markdownCss', '')

    if MARKER in md:
        print('  already restyled (idempotent)')
        return

    if OLD_HTML not in md:
        sys.exit(f'OLD_HTML pattern not found in markdownTextFunction. Looking for: {OLD_HTML!r}')
    md_new = md.replace(OLD_HTML, NEW_HTML, 1)
    css_new = css + CSS_ADD
    w['config']['settings']['markdownTextFunction'] = md_new
    w['config']['settings']['markdownCss'] = css_new
    print(f'  Title restyled : Donnees PAC N -> PAC HYBRIDE N{{N}} (bloc-title style)')

    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()
