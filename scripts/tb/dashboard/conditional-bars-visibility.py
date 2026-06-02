#!/usr/bin/env python3
"""
Visibilite conditionnelle des barres de navigation :

1) Navbar (md-nav-default) - boutons Defaut/Parametrage :
   - Caches sur le state 'menu' (pas d'entityId)
   - Visibles sur 'default' (avec entityId)
   Mecanisme : reinjecter les regles CSS .nav-btns { display:none } avec
   l'override .md-nav-detail-mode .nav-btns { display:flex } + ajout d'un
   retry/MutationObserver dans le script pour fiabiliser l'attachement de
   la classe (regression sur le precedent fix-navbar-buttons).

2) Topbar (tbr-topbar) - Accueil/Profil/Comptes/Deconnexion :
   - Visibles UNIQUEMENT sur state 'donnees_HP1'
   - Sur les autres states (profil, historique, configuration,
     fault_diagnostic, notifications_admin) : titre seul, pas de boutons
   Mecanisme : add classe .tbr-state-detail au container quand stateId===
   'donnees_HP1', CSS cache .tbr-nav par defaut sauf si .tbr-state-detail.

Idempotent via markers __CONDITIONAL_BARS_NAV__ et __CONDITIONAL_BARS_TOPBAR__.

Usage:
  conditional-bars-visibility.py --pwd <pwd>
"""

import argparse, json, sys, time, urllib.request, urllib.error

DASHBOARD_ID = '0964da30-3e56-11f1-bbfe-e1395562cba0'
NAVBAR_ID    = 'a1b2c3d4-0100-4000-a000-000000000010'
TOPBAR_ID    = 'a1b2c3d4-0200-4000-a000-000000000001'
BASE_URL     = 'https://thingsboard.tsmart.fr'

NAV_MARKER    = '__CONDITIONAL_BARS_NAV__'
TOPBAR_MARKER = '__CONDITIONAL_BARS_TOPBAR__'

# --- Navbar : CSS rules a ajouter (si pas deja presentes) ---
NAV_CSS_RULES = """
/* """ + NAV_MARKER + """ : visibilite conditionnelle .nav-btns selon state */
.md-nav .nav-btns { display: none; }
.md-nav.md-nav-detail-mode .nav-btns { display: flex; }
"""

# --- Navbar : block JS retry pour attacher .md-nav-detail-mode fiablement ---
# Place juste apres l'IIFE existante, ajoute un MutationObserver + retry
NAV_JS_RETRY = """
<script>/* """ + NAV_MARKER + """ : retry mecanisme pour md-nav-detail-mode */
(function(){
  function getStateId(){
    try {
      var raw = new URL(window.location.href).searchParams.get('state');
      if (!raw) return 'menu';
      var arr = JSON.parse(atob(decodeURIComponent(raw)));
      var last = arr[arr.length-1];
      return (last && last.id) || 'menu';
    } catch(_) { return 'menu'; }
  }
  function applyMode(){
    var bar = document.getElementById('md-nav-default');
    if (!bar) return false;
    var sid = getStateId();
    var shouldHaveDetail = (sid !== 'menu');
    bar.classList.toggle('md-nav-detail-mode', shouldHaveDetail);
    return true;
  }
  // Retry initial : DOM peut ne pas etre pret au premier coup
  var attempts = 0;
  function tryApply(){
    if (applyMode() || attempts++ > 20) return;
    setTimeout(tryApply, 100);
  }
  tryApply();
  // Re-apply sur popstate (changement state interne)
  window.addEventListener('popstate', applyMode);
})();
</script>
"""

# --- Topbar : CSS rule a ajouter ---
TOPBAR_CSS_RULES = """
/* """ + TOPBAR_MARKER + """ : .tbr-nav visible uniquement sur donnees_HP1 */
.tbr-topbar .tbr-nav { display: none; }
.tbr-topbar.tbr-state-detail .tbr-nav { display: flex; }
"""

# --- Topbar : block JS qui add classe tbr-state-detail selon stateId ---
TOPBAR_JS_RETRY = """
<script>/* """ + TOPBAR_MARKER + """ : add classe tbr-state-detail si donnees_HP1 */
(function(){
  function getStateId(){
    try {
      var raw = new URL(window.location.href).searchParams.get('state');
      if (!raw) return 'menu';
      var arr = JSON.parse(atob(decodeURIComponent(raw)));
      var last = arr[arr.length-1];
      return (last && last.id) || 'menu';
    } catch(_) { return 'menu'; }
  }
  function applyStateClass(){
    var bar = document.getElementById('tbr-topbar');
    if (!bar) return false;
    bar.classList.toggle('tbr-state-detail', getStateId() === 'donnees_HP1');
    return true;
  }
  var attempts = 0;
  function tryApply(){
    if (applyStateClass() || attempts++ > 20) return;
    setTimeout(tryApply, 100);
  }
  tryApply();
  window.addEventListener('popstate', applyStateClass);
})();
</script>
"""


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


def patch_navbar(dash):
    nv = dash['configuration']['widgets'].get(NAVBAR_ID)
    if not nv: return False, 'Navbar widget not found'
    settings = nv['config']['settings']
    css = settings.get('cardCss', '')
    html = settings.get('cardHtml', '')
    changed = False
    if NAV_MARKER not in css:
        settings['cardCss'] = css.rstrip() + '\n' + NAV_CSS_RULES
        changed = True
    if NAV_MARKER not in html:
        settings['cardHtml'] = html.rstrip() + '\n' + NAV_JS_RETRY
        changed = True
    return changed, 'patched' if changed else 'already patched (idempotent)'


def patch_topbar(dash):
    tb = dash['configuration']['widgets'].get(TOPBAR_ID)
    if not tb: return False, 'Topbar widget not found'
    settings = tb['config']['settings']
    css = settings.get('cardCss', '')
    html = settings.get('cardHtml', '')
    changed = False
    if TOPBAR_MARKER not in css:
        settings['cardCss'] = css.rstrip() + '\n' + TOPBAR_CSS_RULES
        changed = True
    if TOPBAR_MARKER not in html:
        settings['cardHtml'] = html.rstrip() + '\n' + TOPBAR_JS_RETRY
        changed = True
    return changed, 'patched' if changed else 'already patched (idempotent)'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    args = ap.parse_args()

    token = login(args.user, args.pwd)
    dash = http_get(f'/api/dashboard/{DASHBOARD_ID}', token)
    print(f'Dashboard version: {dash["version"]}')
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = f'scripts/tb/dashboard/backup/mes-installations.condbars.{ts}.json'
    with open(backup, 'wb') as f:
        f.write(json.dumps(dash, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'Backup : {backup}')

    nav_changed, nav_msg = patch_navbar(dash)
    print(f'  Navbar : {nav_msg}')
    top_changed, top_msg = patch_topbar(dash)
    print(f'  Topbar : {top_msg}')

    if not nav_changed and not top_changed:
        print('No changes -- exiting')
        return

    resp = http_post('/api/dashboard', dash, token)
    print(f'Posted OK. New version: {resp["version"]}')


if __name__ == '__main__':
    main()
