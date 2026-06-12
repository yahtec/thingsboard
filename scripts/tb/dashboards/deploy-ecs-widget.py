#!/usr/bin/env python3
"""Cree l'etat 'ecs' (si absent) + upsert le widget ECS unifie WID_ECS et son layout.
Lit _src/ecs-unified.fn.js et _src/ecs-unified.css. Idempotent.
Usage: deploy-ecs-widget.py --pwd <pwd> [--dry-run]"""
import argparse, copy, json, os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

STATE = 'ecs'
GRID_TEMPLATE_STATE = 'depart_chauffage'
WID_ECS = 'a1b2c3d4-0720-4000-a000-000000000001'
WID_TEMPLATE = 'a1b2c3d4-0710-4000-a000-000000000001'  # widget chauffage unifie (clone de base)
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

    fn = open(os.path.join(HERE, '_src', 'ecs-unified.fn.js'), encoding='utf-8').read()
    css = open(os.path.join(HERE, '_src', 'ecs-unified.css'), encoding='utf-8').read()
    node_check(fn)

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    tb.backup(dash, 'ecs_state')
    conf = dash['configuration']
    states = conf['states']

    if STATE in states:
        print(f"  [state] '{STATE}' existe deja")
    else:
        grid = copy.deepcopy(states[GRID_TEMPLATE_STATE]['layouts']['main'].get('gridSettings', {}))
        states[STATE] = {'name': 'Eau chaude sanitaire', 'root': False,
                         'layouts': {'main': {'widgets': {}, 'gridSettings': grid}}}
        print(f"  [state] '{STATE}' cree (grid clone de {GRID_TEMPLATE_STATE})")

    if WID_ECS in conf['widgets']:
        base = conf['widgets'][WID_ECS]
    elif WID_TEMPLATE in conf['widgets']:
        base = json.loads(json.dumps(conf['widgets'][WID_TEMPLATE]))
        base['id'] = WID_ECS
    else:
        sys.exit('Ni widget ECS ni template chauffage unifie present — etat inattendu.')
    base['config']['title'] = 'ECS (unifie)'
    base['config']['settings']['markdownTextFunction'] = fn
    base['config']['settings']['markdownCss'] = css
    conf['widgets'][WID_ECS] = base

    # un seul widget sur l'etat (leçon autoFillHeight : jamais de cohabitation)
    states[STATE]['layouts']['main']['widgets'] = {WID_ECS: dict(LAYOUT)}
    print(f'  widget upsert + layout {LAYOUT}')

    if args.dry_run:
        prev = os.path.join(HERE, 'preview-ecs-unified.json')
        open(prev, 'wb').write(json.dumps(dash, ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'[dry-run] preview: {prev}')
        return
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()
