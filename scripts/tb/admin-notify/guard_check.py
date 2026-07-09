#!/usr/bin/env python3
"""Check de présence de la garde site_assigned de la rule chain PAC Hybride Router.
Read-only. Alerte par transition (OK<->DÉRIVE) via email tb-notify. Exit 0=OK, 2=dérive, 1=erreur.

Invariant ré-encodé ici (serveur) ; source de vérité = guard-assign-node.py (dev,
scripts/tb/rule-chain-pac-hybride-router/). Garder les deux synchronisés (test = même câblage)."""
import json
import os
import sys
import time

import common

RC_ID = 'b6af0570-4226-11f1-bbfe-e1395562cba0'
ORIG = 'originator -> device(${id})'
GETATTR = 'load site_assigned'
FILTER = 'Provisionnee ?'
ASSIGN = 'Assign to Yahtec'
GOOD_TARGETS = ['Filter HPs present v2', 'mark active', 'DeviceProfile (alarms)']
STATE_FILE = os.environ.get('GUARD_STATE_FILE', '/home/dump/tb-notify/.guard_check_state.json')


def check_guard(meta):
    """(ok, problems) — vérifie les 5 invariants de la garde contre la metadata."""
    nodes = meta.get('nodes', [])
    conns = meta.get('connections', [])
    names = [n.get('name') for n in nodes]
    idx = {name: i for i, name in enumerate(names)}
    problems = []
    for n in (ORIG, FILTER, ASSIGN, *GOOD_TARGETS):
        if n not in idx:
            problems.append(f'node manquant: {n!r}')
    if ORIG not in idx or FILTER not in idx:
        return (False, problems)

    def targets(from_name, typ):
        fi = idx.get(from_name)
        return {names[c['toIndex']] for c in conns if c['fromIndex'] == fi and c['type'] == typ}

    orig_succ = targets(ORIG, 'Success')
    if GETATTR not in orig_succ:
        problems.append(f'{ORIG} --Success--> {GETATTR} absent (garde non branchée)')
    if ASSIGN in orig_succ:
        problems.append(f'BYPASS: {ORIG} --Success--> {ASSIGN} (garde contournée)')
    if GETATTR in idx and FILTER not in targets(GETATTR, 'Success'):
        problems.append(f'{GETATTR} --Success--> {FILTER} absent (routage interrompu)')
    true_t = targets(FILTER, 'True')
    if true_t != set(GOOD_TARGETS):
        problems.append(f'{FILTER} --True--> {sorted(true_t)} != {GOOD_TARGETS}')
    false_t = targets(FILTER, 'False')
    if false_t != {ASSIGN}:
        problems.append(f'{FILTER} --False--> {sorted(false_t)} != [{ASSIGN!r}]')
    return (len(problems) == 0, problems)


def decide_alert(prev, cur):
    """(should_alert, kind). Alerte seulement sur transition ; jamais sur 1er run OK."""
    if cur == prev:
        return (False, None)
    if cur == 'DRIFT':
        return (True, 'lost')
    if cur == 'OK' and prev == 'DRIFT':
        return (True, 'recovered')
    return (False, None)


def _recipients():
    raw = os.environ.get('GUARD_ALERT_TO') or os.environ.get('PARC_ADMINS_FALLBACK') or ''
    return [e.strip() for e in raw.replace(';', ',').split(',') if e.strip()]


def _read_prev():
    try:
        return json.loads(open(STATE_FILE, encoding='utf-8').read()).get('status')
    except Exception:
        return None


def should_persist(alert_needed, delivered):
    """Persister l'état seulement si aucune alerte n'était requise, ou si elle a été livrée.
    Sinon on NE persiste pas -> la transition est re-détectée au prochain tick et l'alerte retentée."""
    return (not alert_needed) or delivered


def _write_state(status, problems):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            f.write(json.dumps({'status': status, 'ts': time.time(), 'problems': problems}))
    except Exception as e:
        print(f'guard_check: écriture état impossible: {e}', file=sys.stderr)


def main():
    try:
        meta = common.TBClient().get(f'/api/ruleChain/{RC_ID}/metadata')
    except Exception as e:
        print(f'guard_check: fetch metadata échoué: {e}', file=sys.stderr)
        sys.exit(1)
    ok, problems = check_guard(meta)
    cur = 'OK' if ok else 'DRIFT'
    should, kind = decide_alert(_read_prev(), cur)
    delivered = False
    if should:
        to = _recipients()
        if not to:
            print('guard_check: aucun destinataire (GUARD_ALERT_TO/PARC_ADMINS_FALLBACK vides)', file=sys.stderr)
        else:
            if kind == 'lost':
                subject = '⚠ Garde rule-chain PAC Hybride PERDUE'
                html = ('<p>La garde <code>site_assigned</code> n\'est plus correctement câblée :</p><ul>'
                        + ''.join(f'<li>{p}</li>' for p in problems) + '</ul>'
                        + '<p>Réparer : <code>guard-assign-node.py --apply</code> (convergent).</p>'
                        + '<p>⚠ Récupération : re-câbler stoppe la casse mais ne remet PAS les devices '
                          'déjà réassignés à yahtec sous leur site — re-provisioning séparé requis.</p>')
            else:
                subject = '✅ Garde rule-chain PAC Hybride rétablie'
                html = '<p>La garde <code>site_assigned</code> est de nouveau correctement câblée.</p>'
            try:
                common.send_mail(to, subject, html)
                delivered = True
            except Exception as e:
                print(f'guard_check: alerte non envoyée: {e}', file=sys.stderr)
    if should_persist(should, delivered):
        _write_state(cur, problems)
    print(f'guard_check: {cur}' + (f' — {"; ".join(problems)}' if problems else ''))
    sys.exit(0 if ok else 2)


if __name__ == '__main__':
    main()
