#!/usr/bin/env python3
"""
Injecte un compactor JS dans le widget Donnees generales (DG, premier de la
rangee row 7). Au runtime :
- Detecte les widgets de la rangee row 7 (DG + 4 PAC + Chauffage + ECS)
- Pour chaque widget contenant .pac-absent-host -> cache la cellule + width=0
- Repositionne les widgets visibles cote-a-cote en partant de la gauche
- MutationObserver pour re-appliquer en cas de re-render TB

Idempotent via marker __ROW7_COMPACTOR__.

Usage:
  inject-row-compactor.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
BASE_URL     = 'https://thingsboard.tsmart.fr'
DG_WIDGET_ID = 'a1b2c3d4-d600-4000-a000-000000000001'
COMPACTOR_MARKER = '__ROW7_COMPACTOR__'

COMPACTOR_JS = '''
// __ROW7_COMPACTOR__ : reorder row-7 widgets to collapse absent PACs.
// Le widget DG porte ce JS qui repositionne les gridster-items via inline style.
(function() {
    if (window.__row7CompactorInit) return;
    window.__row7CompactorInit = true;

    var ROW7_IDS = [
        'a1b2c3d4-d600-4000-a000-000000000001', // DG (this widget)
        'a1b2c3d4-d600-4000-a000-000000000101', // PAC HP1
        'a1b2c3d4-d600-4000-a000-000000000102', // PAC HP2
        'a1b2c3d4-d600-4000-a000-000000000103', // PAC HP3
        'a1b2c3d4-d600-4000-a000-000000000104', // PAC HP4
        'a1b2c3d4-d600-4000-a000-000000000202', // Chauffage
        'a1b2c3d4-d600-4000-a000-000000000201'  // ECS
    ];

    function findCell(id) {
        // Try multiple selectors -- TB DOM may differ
        var sels = [
            'tb-widget-container[id="' + id + '"]',
            '[data-widget-id="' + id + '"]',
            '#widget-' + id,
            'tb-widget[id="' + id + '"]'
        ];
        for (var i = 0; i < sels.length; i++) {
            var el = document.querySelector(sels[i]);
            if (el) return el.closest('gridster-item') || el.closest('.gridster-item');
        }
        return null;
    }

    function reposition() {
        var cells = [];
        ROW7_IDS.forEach(function(id) {
            var c = findCell(id);
            if (c) cells.push({id: id, cell: c});
        });
        if (!cells.length) return;

        // Determine base x position : first cell's current offsetLeft
        var firstCell = cells[0].cell;
        var baseX = firstCell.offsetLeft;
        var baseY = firstCell.offsetTop;
        var cellW = firstCell.offsetWidth;
        var cellH = firstCell.offsetHeight;
        var gap = 10; // margin

        var visIdx = 0;
        cells.forEach(function(item) {
            var hasAbsent = item.cell.querySelector('.pac-absent-host');
            if (hasAbsent) {
                item.cell.style.setProperty('display', 'none', 'important');
                return;
            }
            // Visible: reposition
            item.cell.style.removeProperty('display');
            // Cancel gridster transform, use absolute left
            item.cell.style.setProperty('transform', 'none', 'important');
            item.cell.style.setProperty('left', (baseX + visIdx * (cellW + gap)) + 'px', 'important');
            item.cell.style.setProperty('top', baseY + 'px', 'important');
            item.cell.style.setProperty('width', cellW + 'px', 'important');
            item.cell.style.setProperty('height', cellH + 'px', 'important');
            item.cell.style.setProperty('transition', 'left 0.2s', 'important');
            visIdx++;
        });
    }

    // Run on a delay to let TB finish initial render
    setTimeout(reposition, 600);
    setTimeout(reposition, 1500);
    setTimeout(reposition, 3000);

    // Observe for re-renders (window resize, state change, etc.)
    var obs = new MutationObserver(function(mutations) {
        // Debounce
        if (window.__row7ReposPending) return;
        window.__row7ReposPending = true;
        setTimeout(function() {
            window.__row7ReposPending = false;
            reposition();
        }, 300);
    });
    obs.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['style']});

    // Also on window resize
    window.addEventListener('resize', function() {
        setTimeout(reposition, 100);
    });
})();
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
    backup = f'scripts/tb/dashboard/backup/mes-installations.compactor.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup: {backup}')

    w = dash['configuration']['widgets'][DG_WIDGET_ID]
    md = w['config']['settings'].get('markdownTextFunction', '')
    if COMPACTOR_MARKER in md:
        print('  compactor already present')
    else:
        # Inject the JS snippet (as inline script via setTimeout in markdownTextFunction)
        snippet = f'''
// {COMPACTOR_MARKER}
setTimeout(function() {{
{COMPACTOR_JS}
}}, 0);
'''
        # Insert right before the final `return h;`
        last_return = md.rfind('return h')
        if last_return < 0:
            sys.exit('Could not find "return h" in DG markdownTextFunction')
        md_new = md[:last_return] + snippet + '\n' + md[last_return:]
        w['config']['settings']['markdownTextFunction'] = md_new
        print('  compactor JS injected in DG markdownTextFunction')

    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()
