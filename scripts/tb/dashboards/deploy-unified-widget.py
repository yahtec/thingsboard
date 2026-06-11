#!/usr/bin/env python3
"""Upsert le widget unifie WID_UNIFIED dans donnees_HP1 + applique le layout de phase.
Lit _src/unified.fn.js et _src/unified.css. Idempotent (ecrase toujours).
Usage: deploy-unified-widget.py --pwd <pwd> [--phase 1..5] [--dry-run]"""
import argparse, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WID_UNIFIED = 'a1b2c3d4-0700-4000-a000-000000000001'
WID_TEMPLATE = 'a1b2c3d4-0001-4000-a000-000000000001'  # PAC chart existant (clone de base)
NODE = r'c:\Projets\TB\thingsboard\ui-ngx\target\node\node.exe'
HERE = os.path.dirname(os.path.abspath(__file__))

LAYOUTS = {
    1: {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 18, 'mobileOrder': 0, 'mobileHeight': 24},
    2: {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 26, 'mobileOrder': 0, 'mobileHeight': 30},
    3: {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 32, 'mobileOrder': 0, 'mobileHeight': 36},
    4: {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 34, 'mobileOrder': 0, 'mobileHeight': 38},
    5: {'col': 0, 'row': 0, 'sizeX': 24, 'sizeY': 40, 'mobileOrder': 0, 'mobileHeight': 44},
}

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
    ap.add_argument('--phase', type=int, default=1)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    fn = open(os.path.join(HERE, '_src', 'unified.fn.js'), encoding='utf-8').read()
    css = open(os.path.join(HERE, '_src', 'unified.css'), encoding='utf-8').read()
    node_check(fn)

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    tb.backup(dash, f'unified_p{args.phase}')
    conf = dash['configuration']

    # Si le widget unifie existe deja (phases 2+, ou apres retrait des legacy),
    # on met a jour EN PLACE. Sinon (1er deploiement) on clone le template PAC chart.
    if WID_UNIFIED in conf['widgets']:
        base = conf['widgets'][WID_UNIFIED]
    elif WID_TEMPLATE in conf['widgets']:
        base = json.loads(json.dumps(conf['widgets'][WID_TEMPLATE]))
        base['id'] = WID_UNIFIED
    else:
        sys.exit('Ni widget unifie ni template present — etat inattendu.')
    base['config']['title'] = 'PAC Hybride (unifie)'
    base['config']['settings']['markdownTextFunction'] = fn
    base['config']['settings']['markdownCss'] = css
    conf['widgets'][WID_UNIFIED] = base

    lay = conf['states']['donnees_HP1']['layouts']['main']['widgets']
    lay[WID_UNIFIED] = dict(LAYOUTS[args.phase])
    # Pousse les widgets legacy SOUS le widget unifie (rows >= 100), de facon
    # idempotente : row<100 -> row%100+100 (stable si deja >=100). Evite le
    # chevauchement gridster (unifie occupe rows 0..40) tant que legacy reste
    # en place pour comparaison (retire en phase 5).
    pushed = 0
    for wid, l in lay.items():
        if wid == WID_UNIFIED:
            continue
        if l.get('row', 0) < 100:
            l['row'] = (l['row'] % 100) + 100
            pushed += 1
    print(f'  widget upsert + layout phase {args.phase}: {LAYOUTS[args.phase]} ; legacy pousses sous row 100: {pushed}')

    if args.dry_run:
        prev = os.path.join(HERE, f'preview-unified-p{args.phase}.json')
        open(prev, 'wb').write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] preview: {prev}')
        return
    tb.post_dashboard(dash, t)

if __name__ == '__main__':
    main()
