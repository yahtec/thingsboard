#!/usr/bin/env python3
"""Construction des patchs de source widget pour les registres capteurs gaz.

Logique pure : aucun appel reseau, entierement testable hors ligne. Les
enveloppes REST (patch-*.py) se contentent d'appeler ces fonctions.

Principe : la logique d'affichage vit dans _src/gas_lib.js, injectee telle
quelle en tete de chaque controllerScript. Les blocs conditionnels ecrits a la
main dans les widgets sont remplaces par un appel a cette lib.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GAS_LIB_PATH = os.path.join(HERE, '_src', 'gas_lib.js')

# Marqueurs encadrant la lib injectee. Ils rendent l'injection REMPLACABLE : sans eux,
# une evolution de _src/gas_lib.js ne pourrait plus atteindre un widget deja patche.
LIB_BEGIN = '/* __GAS_LIB_BEGIN__ */'
LIB_END = '/* __GAS_LIB_END__ */'

# Presence du marqueur d'ouverture = lib deja injectee (donc a remplacer, pas a ajouter).
DONE_MARK = LIB_BEGIN

LEGACY_MARK = 'root.__gasLib = {'   # lib injectee sans marqueurs (avant cette tache)
WIDGET_START = 'self.onInit'        # premiere ligne du code propre au widget

# Cible -> (objet JS, suffixe de champ, prefixe de libelle d'origine)
TARGETS = {
    'HP':   {'obj': 'hp',   'sfx': 'R290'},
    'boil': {'obj': 'boil', 'sfx': 'G20'},
}


class AnchorError(RuntimeError):
    """Une ancre de remplacement est absente ou presente plusieurs fois."""


def load_gas_lib():
    """Contenu de _src/gas_lib.js, sans modification."""
    with open(GAS_LIB_PATH, encoding='utf-8') as f:
        return f.read()


def _lib_block():
    return LIB_BEGIN + '\n' + load_gas_lib().rstrip('\n') + '\n' + LIB_END + '\n'


def inject_lib(controller_script):
    """Injecte la lib, ou remplace le bloc deja present. Idempotent par remplacement."""
    bloc = _lib_block()
    i = controller_script.find(LIB_BEGIN)
    if i < 0:
        return bloc + controller_script
    j = controller_script.find(LIB_END, i)
    if j < 0:
        raise AnchorError('marqueur de fin de lib absent -- source live incoherente')
    return controller_script[:i] + bloc + controller_script[j + len(LIB_END) + 1:]


def _strip_legacy_lib(controller_script):
    """Retire une lib injectee sans marqueurs. Le code propre au widget commence a
    `self.onInit` dans les trois widget_types concernes, et la lib n'en contient pas :
    c'est donc une frontiere fiable et verifiable."""
    if WIDGET_START in load_gas_lib():
        raise AnchorError(
            f'{WIDGET_START!r} apparait maintenant dans _src/gas_lib.js -- la frontiere '
            'de migration heritee n\'est plus fiable, decoupe refusee')
    i = controller_script.find(WIDGET_START)
    if i < 0:
        raise AnchorError('debut du code widget introuvable -- migration impossible')
    return controller_script[i:]


def _old_block(obj, sfx):
    """Bloc conditionnel ecrit a la main dans la source live (sans saut de ligne)."""
    label = 'Concentration ' + sfx
    return (
        "({obj}.con{sfx}!=null?kv('{label}',{obj}.con{sfx}*0.1,' %LFL',1)"
        "+'<div class=\"pd-kv\"><span class=\"k\">Capteur {sfx}</span><span class=\"v\">'"
        "+({obj}.err{sfx}==null?'\u2014':(Number({obj}.err{sfx})===0?'OK':String({obj}.err{sfx})))"
        "+'</span></div>':'')"
    ).format(obj=obj, sfx=sfx, label=label)


def table_replacements(target):
    """[(nom, ANCIEN, NOUVEAU)] pour un widget de table."""
    t = TARGETS[target]
    return [(
        f'lignes gaz {t["sfx"]}',
        _old_block(t['obj'], t['sfx']),
        f"window.__gasLib.rows('{t['sfx']}',{t['obj']})",
    )]


def patch_table(controller_script, target):
    """(nouvelle_source, notes). Idempotent."""
    if LIB_BEGIN in controller_script:
        return inject_lib(controller_script), ['appels deja en place, lib rafraichie']
    if LEGACY_MARK in controller_script:
        return (inject_lib(_strip_legacy_lib(controller_script)),
                ['lib heritee sans marqueurs -> migree et rafraichie'])
    notes = []
    out = controller_script
    for name, old, new in table_replacements(target):
        n = out.count(old)
        if n != 1:
            raise AnchorError(f'[{name}] ancre {n}x (attendu 1) -- source live a change')
        out = out.replace(old, new, 1)
        notes.append(f'[{name}] OK ({len(old)} -> {len(new)} c)')
    out = inject_lib(out)
    notes.append(f'lib injectee ({len(load_gas_lib())} c)')
    return out, notes


# ---------- widget Diagnostic defaut (tduo.fault_diagnostic) ----------

# Libelles ASCII : le bloc gaz voisin de KEY_META le fait deja explicitement.
DIAG_KEY_META = """    gas_r290_leak     :{l:'Alarme fuite R290',u:'',s:1,d:0},
    gas_g20_leak      :{l:'Alarme fuite G20', u:'',s:1,d:0},
    gas_r290_op_mode  :{l:'Mode capteur R290',u:'',s:1,d:0},
    gas_g20_op_mode   :{l:'Mode capteur G20', u:'',s:1,d:0},
    gas_r290_leak_thr :{l:'Seuil alarme R290',u:'%LFL',s:0.1,d:1},
    gas_g20_leak_thr  :{l:'Seuil alarme G20', u:'%LFL',s:0.1,d:1},
    gas_r290_temp     :{l:'T capteur R290',u:'°C',s:0.1,d:1},
    gas_g20_temp      :{l:'T capteur G20', u:'°C',s:0.1,d:1},
    gas_r290_hum      :{l:'HR capteur R290',u:'%RH',s:0.1,d:1},
    gas_g20_hum       :{l:'HR capteur G20', u:'%RH',s:0.1,d:1},
    gas_r290_fw_ver   :{l:'Version capteur R290',u:'',s:1,d:0,f:'ver'},
    gas_g20_fw_ver    :{l:'Version capteur G20', u:'',s:1,d:0,f:'ver'},
    gas_r290_spec_ver :{l:'Version protocole R290',u:'',s:1,d:0,f:'ver'},
    gas_g20_spec_ver  :{l:'Version protocole G20', u:'',s:1,d:0,f:'ver'},
    gas_r290_addr     :{l:'Adresse bus R290',u:'',s:1,d:0},
    gas_g20_addr      :{l:'Adresse bus G20', u:'',s:1,d:0},
    gas_r290_gas_type :{l:'Type de gaz R290 (code brut)',u:'',s:1,d:0},
    gas_g20_gas_type  :{l:'Type de gaz G20 (code brut)', u:'',s:1,d:0},
    gas_r290_life_days :{l:'Duree de service R290',u:'j',s:1,d:0},
    gas_g20_life_days  :{l:'Duree de service G20', u:'j',s:1,d:0},
    gas_r290_life_hours:{l:'Duree de service R290 (heures)',u:'h',s:1,d:0},
    gas_g20_life_hours :{l:'Duree de service G20 (heures)', u:'h',s:1,d:0},
    gas_r290_life_warn_thr :{l:'Seuil avertissement fin de vie R290',u:'j',s:1,d:0},
    gas_g20_life_warn_thr  :{l:'Seuil avertissement fin de vie G20', u:'j',s:1,d:0},
    gas_r290_life_alarm_thr:{l:'Seuil fin de vie R290',u:'j',s:1,d:0},
    gas_g20_life_alarm_thr :{l:'Seuil fin de vie G20', u:'j',s:1,d:0},
"""

# ENUM_LABELS accepte les accents : ses voisins en contiennent.
DIAG_ENUMS = """    gas_r290_leak:{0:'non',1:'oui'},
    gas_g20_leak :{0:'non',1:'oui'},
    gas_r290_op_mode:{0:'démarrage',1:'mesure'},
    gas_g20_op_mode :{0:'démarrage',1:'mesure'},
"""

_DIAG_META_OLD = (
    "    gas_r290_err :{l:'Defaut capteur R290 (registre)',u:'',s:1,d:0},\n"
    "    gas_g20_err  :{l:'Defaut capteur G20 (registre)', u:'',s:1,d:0},\n"
)

_DIAG_META_NEW = (
    "    gas_r290_err :{l:'Defaut capteur R290 (registre)',u:'',s:1,d:0,f:'errbits'},\n"
    "    gas_g20_err  :{l:'Defaut capteur G20 (registre)', u:'',s:1,d:0,f:'errbits'},\n"
    + DIAG_KEY_META
)

_DIAG_ENUM_OLD = (
    "var ENUM_LABELS = {\n"
    "    gas_r290_err:{0:'OK'},\n"
    "    gas_g20_err :{0:'OK'},\n"
)

_DIAG_ENUM_NEW = _DIAG_ENUM_OLD + DIAG_ENUMS

# fmtVal : on route vers la lib AVANT la consultation de ENUM_LABELS, pour que
# f:'errbits' prime sur l'entree {0:'OK'} deja presente.
_DIAG_FMT_OLD = (
    "function fmtVal(k,v){\n"
    "    if(v==null||isNaN(v)) return '—';\n"
    "    var m=metaFor(k);\n"
)

_DIAG_FMT_NEW = _DIAG_FMT_OLD + (
    "    if(m.f==='ver'){ var _vv=window.__gasLib.fmtVer(v); return _vv==null?'—':_vv; }\n"
    "    if(m.f==='errbits'){ var _eb=window.__gasLib.decodeErr(v); return _eb==null?'—':_eb; }\n"
)


def diag_replacements():
    """[(nom, ANCIEN, NOUVEAU)] pour tduo.fault_diagnostic."""
    return [
        ('KEY_META gaz', _DIAG_META_OLD, _DIAG_META_NEW),
        ('ENUM_LABELS gaz', _DIAG_ENUM_OLD, _DIAG_ENUM_NEW),
        ('fmtVal formateurs', _DIAG_FMT_OLD, _DIAG_FMT_NEW),
    ]


def patch_diag(controller_script):
    """(nouvelle_source, notes). Idempotent, avec les trois memes cas que patch_table :
    marqueurs presents -> rafraichissement ; lib heritee sans marqueurs -> migration ;
    source vierge -> remplacement des ancres puis injection."""
    if LIB_BEGIN in controller_script:
        return inject_lib(controller_script), ['appels deja en place, lib rafraichie']
    if LEGACY_MARK in controller_script:
        return (inject_lib(_strip_legacy_lib(controller_script)),
                ['lib heritee sans marqueurs -> migree et rafraichie'])
    notes = []
    out = controller_script
    for name, old, new in diag_replacements():
        n = out.count(old)
        if n != 1:
            raise AnchorError(f'[{name}] ancre {n}x (attendu 1) -- source live a change')
        out = out.replace(old, new, 1)
        notes.append(f'[{name}] OK (+{len(new) - len(old)}c)')
    out = inject_lib(out)
    notes.append(f'lib injectee ({len(load_gas_lib())} c)')
    return out, notes


# ---------- instance du graphe Gaz / Securite ----------

GAS_CHART_WIDGET_ID = 'a1b2c3d4-0730-4000-a000-000000000701'

# Le seuil est lu dans la telemetrie, jamais code en dur (regle R4).
THRESHOLD_SERIES = [
    {'field': 'HP.leakThresR290', 'label': 'Seuil R290', 'unit': '%LFL',
     'scale': 0.1, 'color': '#9e9e9e'},
    {'field': 'boil.leakThresG20', 'label': 'Seuil G20', 'unit': '%LFL',
     'scale': 0.1, 'color': '#bdbdbd'},
]


def add_threshold_series(settings):
    """(nouveaux_settings, note). Idempotent, et ramene une serie de seuil divergente
    a la forme canonique. Sur le chemin « rien a faire », renvoie l'objet recu tel quel."""
    out = dict(settings)
    series = [dict(s) for s in out.get('series', [])]
    canon = {s['field']: s for s in THRESHOLD_SERIES}
    corrigees = []
    for i, s in enumerate(series):
        f = s.get('field')
        if f in canon and s != canon[f]:
            series[i] = dict(canon[f])
            corrigees.append(f)
    presents = {s.get('field') for s in series}
    ajoutes = [dict(s) for s in THRESHOLD_SERIES if s['field'] not in presents]
    if not ajoutes and not corrigees:
        return settings, 'series de seuil deja conformes (skip)'
    out['series'] = series + ajoutes
    notes = []
    if corrigees:
        notes.append('corrigees: ' + ', '.join(corrigees))
    if ajoutes:
        notes.append('ajoutees: ' + ', '.join(s['field'] for s in ajoutes))
    return out, ' ; '.join(notes)


# ---------- widget timeline des registres (tsmart.gas_registers) ----------

GAS_REGISTERS_FQN = 'tsmart.gas_registers'
GAS_REGISTERS_WIDGET_ID = 'a1b2c3d4-0740-4000-a000-000000000701'
DIAG_STATE = 'fault_diagnostic'
DIAG_WIDGET_ID = 'fa5e1c00-1234-1234-1234-fa017d106057'
GAS_REGISTERS_LAYOUT = {'col': 0, 'row': 15, 'sizeX': 24, 'sizeY': 8,
                        'mobileOrder': 2, 'mobileHeight': 10}

_LEAK_MAP = {0: {'t': 'non', 'c': '#2e7d32'}, 1: {'t': 'ALARME FUITE', 'c': '#e53935'}}
_MODE_MAP = {0: {'t': 'demarrage', 'c': '#f9a825'}, 1: {'t': 'mesure', 'c': '#2e7d32'}}

# Une piste par registre. Les pistes sans donnee ne sont pas dessinees (R3), donc
# les pistes d'un circuit non instrumente restent silencieuses.
LANES = [
    {'field': 'HP.leakR290', 'label': 'Alarme fuite R290', 'map': _LEAK_MAP},
    {'field': 'boil.leakG20', 'label': 'Alarme fuite G20', 'map': _LEAK_MAP},
    {'field': 'HP.opModeR290', 'label': 'Mode capteur R290', 'map': _MODE_MAP},
    {'field': 'boil.opModeG20', 'label': 'Mode capteur G20', 'map': _MODE_MAP},
    {'field': 'HP.errR290', 'label': 'Defauts capteur R290', 'kind': 'errbits'},
    {'field': 'boil.errG20', 'label': 'Defauts capteur G20', 'kind': 'errbits'},
    {'field': 'HP.leakThresR290', 'label': 'Seuil R290', 'kind': 'value',
     'scale': 0.1, 'unit': '%LFL', 'd': 1},
    {'field': 'boil.leakThresG20', 'label': 'Seuil G20', 'kind': 'value',
     'scale': 0.1, 'unit': '%LFL', 'd': 1},
    {'field': 'HP.addrR290', 'label': 'Adresse bus R290', 'kind': 'value'},
    {'field': 'boil.addrG20', 'label': 'Adresse bus G20', 'kind': 'value'},
    {'field': 'HP.gasTypeR290', 'label': 'Type de gaz R290 (brut)', 'kind': 'value'},
    {'field': 'boil.gasTypeG20', 'label': 'Type de gaz G20 (brut)', 'kind': 'value'},
]
