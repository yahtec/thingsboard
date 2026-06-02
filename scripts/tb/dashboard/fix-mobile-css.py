#!/usr/bin/env python3
"""
Ajoute du CSS mobile-specific dans configuration.settings.customCss pour
debloquer le rendu des markdown_cards sur smartphones :

- Sur mobile (max-width 900px), tb-markdown-view est en height:auto
  (override existant). Mais .bloc-container utilise height:100% -> 100% de
  auto = 0, donc le contenu collapse.
- Fix : forcer .bloc-container et .bloc-body en min-height pour qu'ils
  affichent leur contenu.

Idempotent via marker.

Usage:
  fix-mobile-css.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'
CSS_MARKER   = '/* === mobile-bloc-container-fix === */'
CSS_BLOCK = f'''
{CSS_MARKER}
@media (max-width: 900px) {{
  .bloc-container {{
    height: auto !important;
    min-height: 320px !important;
  }}
  .bloc-body {{
    min-height: 200px !important;
    flex: 1 1 auto !important;
  }}
  /* Make sure the markdown wrapper gives content room */
  tb-markdown, .tb-markdown-view, .markdown-card-container {{
    min-height: 320px !important;
  }}
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
    backup = f'scripts/tb/dashboard/backup/mes-installations.mobcss.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup: {backup}')

    settings = dash['configuration'].setdefault('settings', {})
    css = settings.get('customCss', '')
    if CSS_MARKER in css:
        print('  CSS deja injecte (idempotent)')
    else:
        settings['customCss'] = css + '\n' + CSS_BLOCK
        print('  CSS mobile-bloc-container-fix injecte dans customCss')

    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()
