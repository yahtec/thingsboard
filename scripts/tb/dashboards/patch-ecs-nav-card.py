#!/usr/bin/env python3
"""Rend la carte 'Module ECS' du widget Donnees generales (etat default)
cliquable -> goState('ecs'), UNIQUEMENT si pac_v2.type vaut 2 ou 3.
Idempotent : marker __ECSNAV_V1__.
Usage: patch-ecs-nav-card.py --pwd <pwd> [--dry-run]"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib_tb as tb

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

WID_UNITE = 'a1b2c3d4-d600-4000-a000-000000000001'
MARKER = '__ECSNAV_V1__'


def must_replace(s, old, new, label, count=1):
    n = s.count(old)
    if n != count:
        sys.exit(f'[{label}] anchor trouve {n} fois (attendu {count}) : {old[:80]!r}')
    return s.replace(old, new, count)


OLD_OPEN = """function buildECS(e) {
    var h = '';
    h += '<div class="bloc ecs-bloc">';"""
NEW_OPEN = """function buildECS(e) {
    var h = '';
    // """ + MARKER + """ : carte cliquable si module ECS present (type 2 ou 3)
    var _t = parseInt(e['type'] || 0);
    var _nav = (_t === 2 || _t === 3);
    h += '<div class="bloc ecs-bloc"' + (_nav ? ' data-ecsnav="1" role="button" tabindex="0" aria-label="Voir ECS"' : '') + '>';"""

OLD_CLOSE = """    h += row('Consigne', fv(e['dhw_tSet'], ' C'));
    h += '</div></div>';
    return h;
}"""
NEW_CLOSE = """    h += row('Consigne', fv(e['dhw_tSet'], ' C'));
    if (_nav) h += '<div class="detail-link">Voir détails →</div>';
    h += '</div></div>';
    return h;
}"""

OLD_CLICK = """        var hb = t.closest('.heat-bloc[data-heatnav]');"""
NEW_CLICK = """        var eb = t.closest('.ecs-bloc[data-ecsnav]');
        if (eb) { ev.preventDefault(); goState('ecs'); return; }
        var hb = t.closest('.heat-bloc[data-heatnav]');"""

OLD_KEY = """        if (t.classList.contains('heat-bloc')) { ev.preventDefault(); goState('depart_chauffage'); return; }"""
NEW_KEY = """        if (t.classList.contains('ecs-bloc') && t.hasAttribute('data-ecsnav')) { ev.preventDefault(); goState('ecs'); return; }
        if (t.classList.contains('heat-bloc')) { ev.preventDefault(); goState('depart_chauffage'); return; }"""

CSS_EXTRA = """
/* __ECSNAV_CSS__ */
.ecs-bloc[data-ecsnav] { cursor: pointer; transition: box-shadow 0.2s, transform 0.15s; -webkit-tap-highlight-color: rgba(198, 40, 40, 0.15); }
.ecs-bloc[data-ecsnav]:hover { box-shadow: 0 4px 16px rgba(198, 40, 40, 0.25); transform: translateY(-2px); }
.ecs-bloc[data-ecsnav]:active { transform: translateY(0); box-shadow: 0 1px 4px rgba(198, 40, 40, 0.35); }
.ecs-bloc[data-ecsnav]:focus-visible { outline: 2px solid #c62828; outline-offset: 2px; }
.ecs-bloc[data-ecsnav] .detail-link { color: #c62828; }
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    t = tb.token_or_login(args.user, args.pwd)
    dash = tb.get_dashboard(t)
    conf = dash['configuration']
    if WID_UNITE not in conf['widgets']:
        sys.exit(f'widget Donnees generales absent : {WID_UNITE}')
    c = conf['widgets'][WID_UNITE]['config']
    fn = c['settings']['markdownTextFunction']
    if MARKER in fn:
        print('  Already patched (idempotent skip)')
        return

    fn = must_replace(fn, OLD_OPEN, NEW_OPEN, 'ecs-bloc open')
    fn = must_replace(fn, OLD_CLOSE, NEW_CLOSE, 'ecs-bloc close')
    fn = must_replace(fn, OLD_CLICK, NEW_CLICK, 'click handler')
    fn = must_replace(fn, OLD_KEY, NEW_KEY, 'keydown handler')

    if args.dry_run:
        print('DRY-RUN: 4 remplacements OK. No POST.')
        return

    tb.backup(dash, 'ecsnav')
    c['settings']['markdownTextFunction'] = fn
    c['settings']['markdownCss'] = c['settings'].get('markdownCss', '') + CSS_EXTRA
    tb.post_dashboard(dash, t)


if __name__ == '__main__':
    main()
