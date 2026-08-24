#!/usr/bin/env python3
"""Cree le widget_type tsmart.gas_registers (clone structurel de tsmart.pac_chart)
et insere son instance sous le widget Diagnostic defaut.

Le clone reprend les champs structurels du type existant (bundle, schemas,
defaultConfig) : c'est le moyen le plus sur d'obtenir un widget_type valide sans
deviner les champs attendus par TB.

Idempotent. Usage:
  set TB_TOKEN=<jwt frais>   (ou --pwd <pwd>)
  python deploy-gas-registers-widget.py [--dry-run] [--keep-autofill]
"""
import argparse
import copy
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'widgets'))
sys.path.insert(0, os.path.join(HERE, '..', 'dashboards'))

import _lib_tb as tb            # noqa: E402
import _wt_patch as wt          # noqa: E402
import gas_patch_lib as lib     # noqa: E402

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

NODE = r'c:\Projets\TB\thingsboard\ui-ngx\target\node\node.exe'
SRC = os.path.join(HERE, '_src')
TEMPLATE_FQN = 'tsmart.pac_chart'


def node_check(js):
    """Meme garde que deploy-ecs-widget.py : refuser de deployer du JS invalide.

    Le fichier temporaire est ecrit dans le repertoire courant (pas via le
    repertoire temp par defaut de tempfile) : sous Windows, quand ce script
    tourne dans un shell POSIX (Git Bash), tempfile.gettempdir() peut renvoyer
    un chemin /tmp que le node.exe natif ne resout pas -- node --check
    echouerait alors sur un probleme d'environnement, pas de syntaxe.
    """
    path = os.path.join(os.getcwd(), '_gas_registers_node_check.tmp.js')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('var self={},window={},localStorage={},fetch=function(){};\n' + js)
    try:
        r = subprocess.run([NODE, '--check', path], capture_output=True, text=True)
    finally:
        os.unlink(path)
    if r.returncode != 0:
        sys.exit('node --check ECHEC:\n' + r.stderr[:1200])
    print('  node --check OK')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--user', default='je@yahtec.com')
    ap.add_argument('--pwd')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--keep-autofill', action='store_true')
    a = ap.parse_args()

    html = open(os.path.join(SRC, 'gas-registers.html'), encoding='utf-8').read()
    css = open(os.path.join(SRC, 'gas-registers.css'), encoding='utf-8').read()
    ctrl = open(os.path.join(SRC, 'gas-registers.controller.js'), encoding='utf-8').read()
    gaslib = lib.load_gas_lib()
    node_check(gaslib + '\n' + ctrl)

    tok = wt.token_or_login(a.user, a.pwd)

    # --- 1. widget_type ---
    # Le GET exige le fqn prefixe ; l'objet renvoye porte un fqn non prefixe, donc le
    # POST avec updateExistingByFqn=true retombe bien sur la bonne cible.
    # `cloned` memorise la branche empruntee : la garde anti-ecrasement plus bas
    # n'a pas le meme invariant a verifier selon l'origine de `w` (correction
    # tour 1 : l'absence de 'id' n'est valable que sur le clone, pas sur l'objet
    # existant renvoye par le GET, qui porte legitimement son propre id).
    cloned = False
    existing_id = None
    try:
        w = wt.get_widget_by_fqn('tenant.' + lib.GAS_REGISTERS_FQN, tok)
        existing_id = w.get('id')
        print(f'  type {lib.GAS_REGISTERS_FQN} existe (v{w.get("version")}) -> mise a jour')
    except SystemExit:
        w = None
    if w is None:
        base = wt.get_widget_by_fqn('tenant.' + TEMPLATE_FQN, tok)
        w = copy.deepcopy(base)
        for champ in ('id', 'createdTime', 'version', 'tenantId'):
            w.pop(champ, None)
        w['fqn'] = lib.GAS_REGISTERS_FQN
        cloned = True
        print(f'  type cree par clone de {TEMPLATE_FQN}')
    w['name'] = 'Registres gaz'
    w['descriptor']['templateHtml'] = html
    w['descriptor']['templateCss'] = css
    w['descriptor']['controllerScript'] = gaslib.rstrip('\n') + '\n' + ctrl
    w['descriptor']['sizeX'] = 24
    w['descriptor']['sizeY'] = 8

    # --- 2. instance dans le dashboard ---
    dash = tb.get_dashboard(tok)
    conf = dash['configuration']
    wid = lib.GAS_REGISTERS_WIDGET_ID
    if wid in conf['widgets']:
        inst = conf['widgets'][wid]
        print('  instance existante -> mise a jour de sa config')
    else:
        modele = conf['widgets'].get(lib.GAS_CHART_WIDGET_ID)
        if modele is None:
            sys.exit('graphe gaz introuvable : impossible de cloner une datasource valide')
        inst = json.loads(json.dumps(modele))
        inst['id'] = wid
        print(f'  instance creee par clone de {lib.GAS_CHART_WIDGET_ID}')
    inst['typeFullFqn'] = 'tenant.' + lib.GAS_REGISTERS_FQN
    inst['config']['title'] = 'Registres gaz'
    inst['config']['settings'] = {'title': 'Registres capteurs gaz', 'lanes': lib.LANES}
    conf['widgets'][wid] = inst

    st = conf['states'].get(lib.DIAG_STATE)
    if st is None:
        sys.exit(f'etat {lib.DIAG_STATE} introuvable')
    main_layout = st['layouts']['main']
    main_layout['widgets'][wid] = dict(lib.GAS_REGISTERS_LAYOUT)
    print(f'  layout {lib.GAS_REGISTERS_LAYOUT}')
    grid = main_layout.setdefault('gridSettings', {})
    if a.keep_autofill:
        print('  autoFillHeight conserve (--keep-autofill) : le diagnostic sera comprime')
    else:
        grid['autoFillHeight'] = False
        grid['mobileAutoFillHeight'] = False
        print('  autoFillHeight -> false sur cet etat (page defilante)')

    if a.dry_run:
        prev = os.path.join(HERE, 'preview-gas-registers.json')
        with open(prev, 'wb') as f:
            f.write(json.dumps({'widgetType': w, 'dashboard': dash},
                               ensure_ascii=False, indent=1).encode('utf-8'))
        print(f'  [dry-run] preview: {prev}')
        return

    # --- garde anti-ecrasement (point de risque majeur) ---
    # Le clone de tsmart.pac_chart sert SEPT graphes du dashboard. Si la
    # substitution de fqn avait echoue, le POST avec updateExistingByFqn=true
    # ecraserait pac_chart lui-meme : l'invariant sur le fqn est donc
    # INCONDITIONNEL, sur les deux branches.
    #
    # L'invariant sur 'id' depend en revanche de la branche empruntee
    # (correction tour 1) :
    #   - clonage : 'id' doit etre absent (c'est l'id du MODELE tant qu'on ne
    #     l'a pas retire ; le laisser trainer ferait POSTer sur l'id du modele) ;
    #   - type deja existant : l'objet vient du GET par le fqn du nouveau type,
    #     il porte donc legitimement son propre id -- on verifie que c'est
    #     toujours celui-la (pas celui du modele), pas qu'il est absent.
    fqn_ok = w.get('fqn') == lib.GAS_REGISTERS_FQN
    if cloned:
        id_ok = 'id' not in w
        id_desc = "cle id absente (clonage)"
    else:
        id_ok = existing_id is not None and w.get('id') == existing_id
        id_desc = "id = celui du type vise (pas celui du modele)"
    print(f'  garde anti-ecrasement : fqn={w.get("fqn")!r} (attendu {lib.GAS_REGISTERS_FQN!r}) '
          f'-> {"OK" if fqn_ok else "ECHEC"} ; {id_desc} -> {"OK" if id_ok else "ECHEC"}')
    if not (fqn_ok and id_ok):
        sys.exit('  ARRET : garde anti-ecrasement echouee -- POST annule pour proteger '
                  f'{TEMPLATE_FQN} et ses sept graphes')

    wt.backup(w, 'gas_registers.widget_type')
    resp = wt.post_widget(w, tok)
    print(f'  widget_type POST OK, version {resp.get("version", "?")}')
    tb.backup(dash, 'gas_registers_widget')
    tb.post_dashboard(dash, tok)


if __name__ == '__main__':
    main()
