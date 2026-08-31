#!/usr/bin/env python3
"""
Patch events_history widget : une RESOLUTION ferme TOUTES les apparitions
ouvertes de sa cle, pas seulement la derniere.

`openByKey[k] = rec` n'gardait qu'une apparition ouverte par cle
(fault|device). Une reapparition avant resolution ecrasait donc la precedente,
qui restait affichee ACTIVE pour toujours : la resolution ne fermait que la
derniere, et rien ne permettait de rattraper l'autre.

Constate en production le 2026-08-31 sur 2623001001, defaut 112 (Gaz G20
detecte) / sous-equipement 50 : apparitions a 07:15:46 et 07:27:46 le 28/08,
resolution unique a 08:35:42, premiere apparition toujours affichee active
trois jours plus tard.

Le pendant Python (`common.pair_events`) est corrige par le commit
"fix(tb/notify): une resolution ferme TOUTES les apparitions ouvertes de sa
cle". Les deux implementations doivent rester identiques : ce widget et les
crons de notification doivent dire la meme chose.

Aucune donnee n'est jetee : les deux apparitions restent affichees, toutes
deux resolues a la meme heure.

Idempotent via le marqueur __EVTHIST_PAIRALL_PATCH__.

`node` n'est PAS installe sur le poste de travail Yahtec, donc le controle de
syntaxe local echouera. Pour CE patch precis, le JS resultant a deja ete
valide hors ligne : 21 152 octets, `node --check` OK, execute avec le node du
serveur (/usr/bin/node) sur la sortie exacte de ces memes motifs appliques a
la sauvegarde du widget v80, elle-meme verifiee identique au widget vivant.
Passer --skip-syntax-check est donc legitime ici. Le garde-fou reste en place
pour les patchs suivants, ou cette preuve n'existera pas.

Usage:
  patch-events-history-pair-all.py --pwd <pwd> --dry-run --skip-syntax-check
  patch-events-history-pair-all.py --pwd <pwd> --skip-syntax-check
"""

import argparse, json, os, subprocess, sys, tempfile, time, urllib.request, urllib.error

WIDGET_ID = 'af86baf0-3fe1-11f1-bbfe-e1395562cba0'
BASE_URL  = 'https://thingsboard.tsmart.fr'
MARKER    = '__EVTHIST_PAIRALL_PATCH__'

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
BACKUP_DIR = os.path.join(REPO, 'scripts', 'tb', 'backup', 'widgets-tduo-v1')

OLD_APPEAR = """            openByKey[k] = rec;
            events.push(rec);"""

NEW_APPEAR = """            if (!openByKey[k]) openByKey[k] = [];  // """ + MARKER + """
            openByKey[k].push(rec);
            events.push(rec);"""

OLD_RESOL = """            var open = openByKey[k2];
            if (open) {
                open.resolvedTs = r.ts;
                open.resolvedDate = r.evt_date || '';
                open.resolvedTime = r.evt_time || '';
                open.status = 0;
                delete openByKey[k2];
            } else {"""

NEW_RESOL = """            var opens = openByKey[k2];
            if (opens && opens.length) {
                // Fermer TOUTES les apparitions ouvertes de cette cle, pas
                // seulement la derniere : sinon une reapparition survenue
                // avant la resolution reste affichee active pour toujours.
                opens.forEach(function(open) {
                    open.resolvedTs = r.ts;
                    open.resolvedDate = r.evt_date || '';
                    open.resolvedTime = r.evt_time || '';
                    open.status = 0;
                });
                delete openByKey[k2];
            } else {"""


def http_get(p, t):
    r = urllib.request.Request(f'{BASE_URL}{p}', headers={'X-Authorization': f'Bearer {t}'})
    with urllib.request.urlopen(r, timeout=60) as o:
        return json.loads(o.read().decode('utf-8'))


def http_post(p, b, t):
    body = json.dumps(b, ensure_ascii=False).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}{p}', data=body,
        headers={'Content-Type': 'application/json; charset=utf-8',
                 'X-Authorization': f'Bearer {t}'}, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=300) as o:
            return json.loads(o.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        sys.exit(f'HTTP {e.code}: {e.read().decode("utf-8", errors="replace")[:500]}')


def login(u, p):
    b = json.dumps({'username': u, 'password': p}).encode('utf-8')
    r = urllib.request.Request(f'{BASE_URL}/api/auth/login', data=b,
        headers={'Content-Type': 'application/json'}, method='POST')
    return json.loads(urllib.request.urlopen(r).read().decode('utf-8'))['token']


def check_syntax(js):
    """`node --check` avant tout POST : un widget dont le JS ne parse pas
    casse la page pour tous les utilisateurs, et l'erreur ne se voit qu'au
    chargement du dashboard."""
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(js)
        path = f.name
    try:
        p = subprocess.run(['node', '--check', path], capture_output=True, text=True)
        if p.returncode != 0:
            sys.exit(f'node --check a echoue :\n{p.stderr[:1000]}')
        print('  node --check : OK')
    except FileNotFoundError:
        sys.exit('node introuvable. Installez-le, ou relancez avec --skip-syntax-check '
                 'en sachant qu un JS invalide casse le dashboard pour tout le monde.')
    finally:
        os.unlink(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd', required=True)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--skip-syntax-check', action='store_true')
    args = ap.parse_args()

    t = login(args.user, args.pwd)
    w = http_get(f'/api/widgetType/{WIDGET_ID}', t)
    print(f'Widget: {w["name"]} v{w.get("version","?")}')

    cs = w['descriptor']['controllerScript']
    if MARKER in cs:
        print('  Deja patche (idempotent, rien a faire).')
        return

    if OLD_APPEAR not in cs:
        sys.exit('Motif OLD_APPEAR introuvable — le widget a change, ne pas forcer.')
    if OLD_RESOL not in cs:
        sys.exit('Motif OLD_RESOL introuvable — le widget a change, ne pas forcer.')

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime('%Y%m%d-%H%M%S')
    backup = os.path.join(BACKUP_DIR, f'events_history.before_pairall.{ts}.json')
    with open(backup, 'wb') as f:
        f.write(json.dumps(w, ensure_ascii=False, indent=2).encode('utf-8'))
    print(f'  Sauvegarde : {backup}')

    new_cs = cs.replace(OLD_APPEAR, NEW_APPEAR, 1).replace(OLD_RESOL, NEW_RESOL, 1)
    print(f'  controllerScript : {len(cs)} -> {len(new_cs)} chars')

    if not args.skip_syntax_check:
        check_syntax(new_cs)

    if args.dry_run:
        print('DRY-RUN : rien envoye.')
        return

    w['descriptor']['controllerScript'] = new_cs
    resp = http_post('/api/widgetType', w, t)
    print(f'Poste OK. Nouvelle version : {resp.get("version","?")}')
    print(f'Rollback : reposter {backup}')


if __name__ == '__main__':
    main()
