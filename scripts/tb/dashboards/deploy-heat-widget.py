#!/usr/bin/env python3
"""Upsert le widget chauffage unifie WID_HEAT dans depart_chauffage + layout.
Lit _src/heat-unified.fn.js et _src/heat-unified.css. Idempotent.
Usage: deploy-heat-widget.py --pwd <pwd> [--dry-run]"""
import argparse, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

STATE = 'depart_chauffage'
WID_HEAT = 'a1b2c3d4-0710-4000-a000-000000000001'
WID_TEMPLATE = 'a1b2c3d4-0501-4000-a000-000000000001'  # Chauffage Chart (clone de base)
NODE = r'c:\Projets\TB\thingsboard\ui-ngx\target\node\node.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
LAYOUT = {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 24, 'mobileOrder': 0, 'mobileHeight': 28}


def node_check(fn_src):
    wrapped = 'function __t(ctx, self, data){\n' + fn_src + '\n}'
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8')
    f.write(wrapped); f.close()
    r = subprocess.run([NODE, '--check', f.name], capture_output=True, text=True)
    os.unlink(f.name)
    if r.returncode != 0:
        sys.exit('node --check ECHEC:\n' + r.stderr[:1200])
    print('  node --check OK')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    fn = open(os.path.join(HERE, '_src', 'heat-unified.fn.js'), encoding='utf-8').read()
    css = open(os.path.join(HERE, '_src', 'heat-unified.css'), encoding='utf-8').read()
    node_check(fn)

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    tb.backup(dash, 'heat_unified')
    conf = dash['configuration']

    if WID_HEAT in conf['widgets']:
        base = conf['widgets'][WID_HEAT]
    elif WID_TEMPLATE in conf['widgets']:
        base = json.loads(json.dumps(conf['widgets'][WID_TEMPLATE]))
        base['id'] = WID_HEAT
    else:
        sys.exit('Ni widget chauffage unifie ni template present — etat inattendu.')
    base['config']['title'] = 'Chauffage (unifie)'
    base['config']['settings']['markdownTextFunction'] = fn
    base['config']['settings']['markdownCss'] = css
    conf['widgets'][WID_HEAT] = base

    lay = conf['states'][STATE]['layouts']['main']['widgets']
    lay[WID_HEAT] = dict(LAYOUT)
    pushed = 0
    for wid, l in lay.items():
        if wid == WID_HEAT:
            continue
        if l.get('row', 0) < 100:
            l['row'] = (l['row'] % 100) + 100
            pushed += 1
    print(f'  widget upsert + layout {LAYOUT} ; legacy pousses sous row 100: {pushed}')

    if args.dry_run:
        prev = os.path.join(HERE, 'preview-heat-unified.json')
        open(prev, 'wb').write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] preview: {prev}')
        return
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()
