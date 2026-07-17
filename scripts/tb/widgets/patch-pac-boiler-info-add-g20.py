#!/usr/bin/env python3
"""Ajoute les lignes gaz G20 (Concentration %LFL + Capteur) a la colonne Chaudiere
du widget tenant.tsmart.pac_boiler_info (page PAC live 'Mes Installations' 0964da30).

Echelle CONFIRMEE (firmware) : concentration = %LFL x10 -> affiche brut*0.1, 1 dec.
Registre errG20 : 0 -> 'OK', sinon brut ; absent -> tuiles masquees (gating conG20).
Idempotent (marqueur 'Concentration G20'). Base sur le controllerScript LIVE.
Spec: docs/superpowers/specs/2026-07-16-gaz-live-telemetrie-page-pac-design.md

Usage: set TB_TOKEN=<jwt frais>  (ou --pwd <pwd>)
       python patch-pac-boiler-info-add-g20.py [--dry-run]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wt_patch as wt

FQN = 'tenant.tsmart.pac_boiler_info'
MARK = 'Concentration G20'

OLD = """kv('Débit eau',boil.qe,' L/h',0)+kv('Vitesse brûleur',boil.rpm,' rpm',0)+kv('Temps de fonctionnement',htime(boil.time),' h',0)+'</div>'+"""
NEW = """kv('Débit eau',boil.qe,' L/h',0)+kv('Vitesse brûleur',boil.rpm,' rpm',0)+kv('Temps de fonctionnement',htime(boil.time),' h',0)+(boil.conG20!=null?kv('Concentration G20',boil.conG20*0.1,' %LFL',1)+'<div class="pd-kv"><span class="k">Capteur G20</span><span class="v">'+(boil.errG20==null?'—':(Number(boil.errG20)===0?'OK':String(boil.errG20)))+'</span></div>':'')+'</div>'+"""


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
    new = wt.apply_replacements(cs, [('G20', OLD, NEW)])
    if a.dry_run:
        print(f'DRY-RUN {len(cs)}->{len(new)}c, pas de POST')
        return
    wt.backup(w, 'pac_boiler_info.before_g20')
    w['descriptor']['controllerScript'] = new
    r = wt.post_widget(w, tok)
    print(f'POST OK v{r.get("version")}')


if __name__ == '__main__':
    main()
