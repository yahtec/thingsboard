#!/usr/bin/env python3
"""Ajoute les lignes gaz R290 (Concentration %LFL + Capteur) a la table PAC du
widget tenant.tsmart.pac_detail_top_wip (page PAC live 'Mes Installations' 0964da30).

Echelle CONFIRMEE (firmware) : concentration = %LFL x10 -> affiche brut*0.1, 1 dec.
Registre errR290 : 0 -> 'OK', sinon brut ; absent -> tuiles masquees (gating conR290).
Idempotent (marqueur 'Concentration R290'). Base sur le controllerScript LIVE.
Spec: docs/superpowers/specs/2026-07-16-gaz-live-telemetrie-page-pac-design.md

Usage: set TB_TOKEN=<jwt frais>  (ou --pwd <pwd>)
       python patch-pac-detail-top-wip-add-r290.py [--dry-run]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wt_patch as wt

FQN = 'tenant.tsmart.pac_detail_top_wip'
MARK = 'Concentration R290'

OLD = """kv('T° surchauffe',hp.tOH,' °C',1)+kv('Temps de fonctionnement',htime(hp.time),' h',0)+'</div></div>';"""
NEW = """kv('T° surchauffe',hp.tOH,' °C',1)+kv('Temps de fonctionnement',htime(hp.time),' h',0)+(hp.conR290!=null?kv('Concentration R290',hp.conR290*0.1,' %LFL',1)+'<div class="pd-kv"><span class="k">Capteur R290</span><span class="v">'+(hp.errR290==null?'—':(Number(hp.errR290)===0?'OK':String(hp.errR290)))+'</span></div>':'')+'</div></div>';"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    tok = wt.token_or_login(a.user, a.pwd)
    w = wt.get_widget_by_fqn(FQN, tok)
    print(f'Widget {w.get("fqn")} v{w.get("version")}')
    cs = w['descriptor']['controllerScript']
    if MARK in cs:
        print('  deja patche (skip)')
        return
    new = wt.apply_replacements(cs, [('R290', OLD, NEW)])
    if a.dry_run:
        print(f'DRY-RUN {len(cs)}->{len(new)}c, pas de POST')
        return
    wt.backup(w, 'pac_detail_top_wip.before_r290')
    w['descriptor']['controllerScript'] = new
    r = wt.post_widget(w, tok)
    print(f'POST OK v{r.get("version")}')


if __name__ == '__main__':
    main()
