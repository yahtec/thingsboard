#!/usr/bin/env python3
"""Construction des patchs de source widget pour les registres capteurs gaz.

Logique pure : aucun appel reseau, entierement testable hors ligne. Les
enveloppes REST (patch-*.py) se contentent d'appeler ces fonctions.

Principe : la logique d'affichage vit dans _src/gas_lib.js, injectee telle
quelle en tete de chaque controllerScript. Les blocs conditionnels ecrits a la
main dans les widgets sont remplaces par un appel a cette lib.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAS_LIB_PATH = os.path.join(HERE, '_src', 'gas_lib.js')

# Meme binaire pour les trois enveloppes REST qui postent du controllerScript :
# node --check est la seule garde contre une virgule oubliee dans gas_lib.js.
NODE_PATH = r'c:\Projets\TB\thingsboard\ui-ngx\target\node\node.exe'

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


def node_check(js):
    """Refuse de continuer si `js` n'est pas syntaxiquement valide pour Node.

    Partagee par les enveloppes REST qui postent du controllerScript
    (patch-gas-state-rows.py, patch-fault-diagnostic-gas-registers.py,
    patch-fault-diagnostic-leak-line.py) : une virgule oubliee dans gas_lib.js ou dans
    un bloc injecte ne doit jamais atteindre la production, quel que soit le script qui
    rejoue le patch.

    Le fichier temporaire est ecrit dans le repertoire courant (pas via le repertoire
    temp par defaut de tempfile) : sous Windows, quand ce script tourne dans un shell
    POSIX (Git Bash), tempfile.gettempdir() peut renvoyer un chemin /tmp que le
    node.exe natif ne resout pas -- node --check echouerait alors sur un probleme
    d'environnement, pas de syntaxe.
    """
    path = os.path.join(os.getcwd(), '_gas_patch_node_check.tmp.js')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('var self={},window={},localStorage={},fetch=function(){};\n' + js)
    try:
        r = subprocess.run([NODE_PATH, '--check', path], capture_output=True, text=True)
    finally:
        os.unlink(path)
    if r.returncode != 0:
        sys.exit('node --check ECHEC:\n' + r.stderr[:1200])
    print('  node --check OK')


def lib_block():
    """Bloc gas_lib.js encadre par LIB_BEGIN/LIB_END, pret a etre concatene devant le
    code propre d'un widget. Utilise par inject_lib() ci-dessous."""
    return LIB_BEGIN + '\n' + load_gas_lib().rstrip('\n') + '\n' + LIB_END + '\n'


def inject_lib(controller_script):
    """Injecte la lib, ou remplace le bloc deja present. Idempotent par remplacement."""
    bloc = lib_block()
    i = controller_script.find(LIB_BEGIN)
    if i < 0:
        return bloc + controller_script
    j = controller_script.find(LIB_END, i)
    if j < 0:
        raise AnchorError('marqueur de fin de lib absent -- source live incoherente')
    # Le bloc genere par lib_block() se termine par LIB_END + un seul '\n'. On ne peut
    # pas supposer que la source relue en porte forcement un a cet endroit precis :
    # sauter systematiquement 1 caractere de plus mangerait le premier caractere du
    # code voisin si ce saut de ligne etait absent, en silence. On retire seulement
    # les sauts de ligne effectivement presents en tete du reste.
    reste = controller_script[j + len(LIB_END):].lstrip('\n')
    return controller_script[:i] + bloc + reste


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


# ---------- widget timeline des registres (tsmart.gas_registers), retire ----------
# Le widget_type et son instance sont retires par retire-gas-registers-widget.py
# (amendement du 2026-08-24 : remplaces par la ligne "alarme capteur", voir
# leakWindow() dans _src/gas_lib.js et diag_leak_replacements() ci-dessous). Ces
# trois constantes restent : le script de retrait en a besoin pour retrouver
# l'instance et l'etat a nettoyer.

GAS_REGISTERS_FQN = 'tsmart.gas_registers'
GAS_REGISTERS_WIDGET_ID = 'a1b2c3d4-0740-4000-a000-000000000701'
DIAG_STATE = 'fault_diagnostic'


# ---------- ligne "alarme capteur" du widget Diagnostic defaut (amendement 2026-08-24) ----------
# Remplace le widget timeline retire ci-dessus : __gasLib.leakWindow() (voir _src/gas_lib.js)
# reduit l'historique pac_v2 a la fenetre pendant laquelle le bit d'alarme est reste a 1,
# seule grandeur fiable a 1 echantillon/minute (la concentration, elle, est evacuee en
# quelques dizaines de secondes). Les trois ancres ci-dessous cablent son affichage dans
# _renderHeader et son chargement paresseux avant _fetchRealtime.

_DIAG_LEAK_LINE_OLD = (
    "          (self._snapTs ? \"<div class='when'>Données envoyées vers le <b>\"+"
    "fmtFull(c.evtTs+30000)+\"</b> · ts snapshot DB <b>\"+fmtFull(self._snapTs)+"
    "\"</b></div>\" : \"\")+\n"
)

_DIAG_LEAK_LINE_NEW = _DIAG_LEAK_LINE_OLD + (
    "          (self._leakLine ? \"<div class='when'>\"+self._leakLine+\"</div>\" : \"\")+\n"
)

_DIAG_LEAK_FETCH_OLD = "self._fetchRealtime = function(){"

# R1 applique a l'echec technique lui-meme : une absence d'information (lib pas
# rafraichie, fetch en erreur) ne doit jamais rendre un ecran silencieux -- c'est
# precisement ce qui a permis au defaut du 2026-08-24 (lib jamais rafraichie) de
# passer inapercu. Ce message est repris tel quel par le test qui verifie que
# gas_patch_lib.py et gas_lib.js restent en phase (test_gas_patch_lib.py).
DIAG_LEAK_UNAVAILABLE_MSG = 'Alarme capteur : lecture indisponible'

# Marqueurs encadrant le bloc _loadLeakLine, sur le modele exact de LIB_BEGIN/LIB_END
# (voir plus haut). Meme raison d'etre : sans eux, une correction de
# _DIAG_LEAK_FETCH_CONTENT (ex. le defaut d'ancrage corrige ci-dessous) ne peut plus
# atteindre un widget deja patche -- patch_diag_leak() verrait DIAG_LEAK_MARK deja
# present, prendrait la branche "ancres deja en place" et s'arreterait sans jamais
# rejouer _DIAG_LEAK_FETCH_CONTENT. C'est exactement ce qui a rendu la correction du
# defaut d'ancrage du 2026-08-24 indeployable en l'etat.
DIAG_LEAK_BEGIN = '/* __GAS_LEAK_BEGIN__ */'
DIAG_LEAK_END = '/* __GAS_LEAK_END__ */'

# Frontiere de debut d'un bloc _loadLeakLine insere AVANT l'introduction de
# DIAG_LEAK_BEGIN/END -- c'est l'etat de prod au 2026-08-24. Ce commentaire est la
# toute premiere ligne du bloc depuis sa version initiale : une frontiere fiable,
# identique que le bloc soit encadre ou non.
DIAG_LEAK_LEGACY_START = "// Ligne « alarme capteur »"

_DIAG_LEAK_FETCH_CONTENT = (
    "// Ligne « alarme capteur » : le bit d'alarme est maintenu 5 min par le capteur, donc\n"
    "// observable a 1/min, contrairement a la concentration qui est evacuee en quelques\n"
    "// dizaines de secondes. Declenchement paresseux depuis _renderHeader.\n"
    "self._loadLeakLine = function(){\n"
    "    var c = self._ctx;\n"
    "    var UNAVAILABLE = '" + DIAG_LEAK_UNAVAILABLE_MSG + "';\n"
    "    if (self._leakLine !== undefined) { return; }\n"
    "    if (!window.__gasLib || typeof window.__gasLib.leakWindow !== 'function') {\n"
    "        self._leakLine = UNAVAILABLE;   // R1 : jamais d'ecran silencieux sur un echec\n"
    "        return;\n"
    "    }\n"
    "    self._leakLine = null;\n"
    "    // ANCRE = c.evtTs (APPARITION du defaut), jamais c.evtResolvedTs (resolution) en\n"
    "    // priorite : la fenetre d'alarme capteur doit encadrer l'apparition du defaut, pas\n"
    "    // sa resolution -- ce choix etait correct dans _fetchRealtime (les tableaux temps\n"
    "    // reel sont envoyes au moment de la resolution) mais faux ici, recopie a tort.\n"
    "    // Defaut constate en prod : un defaut gaz apparu le 08/08 a 12:23:30 et resolu 16\n"
    "    // jours plus tard, le 24/08 a 10:28:20 -- ancrer sur evtResolvedTs cherchait\n"
    "    // l'alarme autour du 24/08 et affichait \"R290 : non\", alors que le bit d'alarme\n"
    "    // valait 1 de 12:23:38 a 12:28:39 le 08/08 (6 echantillons consecutifs, le maintien\n"
    "    // de 5 min du capteur). Une affirmation fausse sur une question de securite est\n"
    "    // pire que pas d'affichage : ne JAMAIS retomber sur evtResolvedTs, sauf si evtTs\n"
    "    // est absent ou nul. NE PAS reintervertir cet ordre.\n"
    "    var probeTs = (c.evtTs && c.evtTs > 0) ? c.evtTs : c.evtResolvedTs;\n"
    "    if (!c.devId || !probeTs) { return; }\n"
    "    fetch('/api/plugins/telemetry/DEVICE/'+c.devId+'/values/timeseries?keys=pac_v2&startTs='+\n"
    "          (probeTs-600000)+'&endTs='+(probeTs+600000)+'&limit=200&orderBy=ASC',\n"
    "          {headers:{'X-Authorization':'Bearer '+getToken()}})\n"
    "      .then(function(r){ return r.json(); })\n"
    "      .then(function(dd){\n"
    "          var hist = ((dd && dd.pac_v2) || []).map(function(x){\n"
    "              var v = null; try { v = JSON.parse(x.value); } catch(e) {}\n"
    "              return [Number(x.ts), v];\n"
    "          }).filter(function(x){ return x[1]; });\n"
    "          var parts = [];\n"
    "          [['R290','HP.leakR290'],['G20','boil.leakG20']].forEach(function(p){\n"
    "              var w = window.__gasLib.leakWindow(hist, p[1], 1);\n"
    "              if (w.alarme === null) { return; }\n"
    "              if (w.alarme) {\n"
    "                  parts.push('<b>'+p[0]+' : oui</b>, de '+fmtTime(w.start)+' a '+\n"
    "                             fmtTime(w.end)+' ('+w.minutes+' min)');\n"
    "              } else {\n"
    "                  parts.push(p[0]+' : non');\n"
    "              }\n"
    "          });\n"
    "          self._leakLine = parts.length\n"
    "            ? ('Alarme capteur sur \\u00b110 min &mdash; ' + parts.join(' \\u00b7 '))\n"
    "            : 'Alarme capteur : aucune donn\\u00e9e capteur sur \\u00b110 min';\n"
    "          self._render();\n"
    "      })\n"
    "      .catch(function(){ self._leakLine = UNAVAILABLE; self._render(); });\n"
    "};\n"
)


def _wrap_marked_block(begin, end, content):
    """Encadre `content` par les marqueurs begin/end. Meme forme que lib_block() pour
    LIB_BEGIN/LIB_END, generalisee a tout bloc insere qui doit rester remplacable."""
    return begin + '\n' + content.rstrip('\n') + '\n' + end + '\n'


def _replace_marked_block(text, begin, end, new_content):
    """Remplace, dans `text`, le contenu encadre par begin/end par new_content ;
    conserve tout le reste de `text` inchange. A appeler seulement quand `begin` est
    deja present (sinon AnchorError). Meme prudence que inject_lib() sur le saut de
    ligne suivant le marqueur de fin : on ne peut pas supposer qu'il en existe
    exactement un dans une source relue, donc on retire seulement ceux effectivement
    presents plutot que de sauter un nombre fixe de caracteres."""
    i = text.find(begin)
    if i < 0:
        raise AnchorError(f'marqueur de debut {begin!r} absent -- appeler seulement si present')
    j = text.find(end, i)
    if j < 0:
        raise AnchorError(f'marqueur de fin {end!r} absent -- source live incoherente')
    reste = text[j + len(end):].lstrip('\n')
    return text[:i] + _wrap_marked_block(begin, end, new_content) + reste


def _leak_fetch_block():
    """Bloc _loadLeakLine courant, encadre par DIAG_LEAK_BEGIN/END et pret a etre
    concatene devant l'ancre _DIAG_LEAK_FETCH_OLD."""
    return _wrap_marked_block(DIAG_LEAK_BEGIN, DIAG_LEAK_END, _DIAG_LEAK_FETCH_CONTENT)


def _refresh_leak_fetch_block(controller_script):
    """Remplace un bloc _loadLeakLine deja encadre par la version courante -- c'est ce
    qui permet a une correction (ex. le defaut d'ancrage) d'atteindre un widget deja
    patche, au lieu d'etre ignoree comme avant l'introduction des marqueurs."""
    return _replace_marked_block(controller_script, DIAG_LEAK_BEGIN, DIAG_LEAK_END,
                                  _DIAG_LEAK_FETCH_CONTENT)


def _migrate_legacy_leak_block(controller_script):
    """Retire un bloc _loadLeakLine insere avant l'introduction des marqueurs (etat de
    prod au 2026-08-24) et le remplace par le bloc courant, encadre -- meme logique que
    _strip_legacy_lib() pour la lib heritee : une frontiere de debut fiable
    (DIAG_LEAK_LEGACY_START, inchangee depuis la premiere version du bloc) et une
    frontiere de fin fiable (_DIAG_LEAK_FETCH_OLD, presente avant et apres patch
    puisque self._fetchRealtime n'est jamais retire)."""
    i = controller_script.find(DIAG_LEAK_LEGACY_START)
    if i < 0:
        raise AnchorError('debut du bloc _loadLeakLine legacy introuvable -- migration impossible')
    j = controller_script.find(_DIAG_LEAK_FETCH_OLD, i)
    if j < 0:
        raise AnchorError(
            'ancre _fetchRealtime introuvable apres le bloc _loadLeakLine legacy -- migration impossible')
    return controller_script[:i] + _leak_fetch_block() + controller_script[j:]


# Pas de saut de ligne supplementaire entre le bloc et l'ancre : _leak_fetch_block()
# se termine deja par exactement un '\n' apres DIAG_LEAK_END (meme convention que
# lib_block()/inject_lib() pour LIB_BEGIN/LIB_END), et _refresh_leak_fetch_block()
# normalise a zero saut de ligne resultant avant de reappliquer ce meme '\n' -- les
# deux chemins doivent produire la meme sortie pour rester idempotents.
_DIAG_LEAK_FETCH_NEW = _leak_fetch_block() + _DIAG_LEAK_FETCH_OLD

_DIAG_LEAK_TRIGGER_OLD = "self._renderHeader = function(){\n    var c = self._ctx;"

_DIAG_LEAK_TRIGGER_NEW = (
    "self._renderHeader = function(){\n    var c = self._ctx;\n    self._loadLeakLine();"
)

# Presence => les trois ancres d'appel sont deja en place. On continue neanmoins
# jusqu'a inject_lib() dans tous les cas (voir patch_diag_leak ci-dessous) : sinon ce
# script dependrait de l'ordre d'execution avec les autres patch-*.py pour que la lib
# effectivement injectee corresponde a l'appel __gasLib.leakWindow qu'il pose. C'est
# exactement le defaut constate en prod le 2026-08-24 (lib jamais rafraichie).
DIAG_LEAK_MARK = 'self._loadLeakLine'


def diag_leak_replacements():
    """[(nom, ANCIEN, NOUVEAU)] pour la ligne "alarme capteur" de tduo.fault_diagnostic."""
    return [
        ('ligne alarme capteur (rendu)', _DIAG_LEAK_LINE_OLD, _DIAG_LEAK_LINE_NEW),
        ('chargement alarme capteur (_loadLeakLine)', _DIAG_LEAK_FETCH_OLD, _DIAG_LEAK_FETCH_NEW),
        ('declenchement paresseux (_renderHeader)', _DIAG_LEAK_TRIGGER_OLD, _DIAG_LEAK_TRIGGER_NEW),
    ]


def patch_diag_leak(controller_script):
    """(nouvelle_source, notes). Trois chemins, dans cet ordre :

    - bloc _loadLeakLine deja encadre (DIAG_LEAK_BEGIN present) -> son contenu est
      REMPLACE par la version courante de _DIAG_LEAK_FETCH_CONTENT. C'est ce qui
      permet a une correction du bloc (ex. le defaut d'ancrage evtTs/evtResolvedTs du
      2026-08-24) d'atteindre un widget deja patche ;
    - bloc present mais SANS marqueurs (DIAG_LEAK_MARK trouve, DIAG_LEAK_BEGIN absent
      -- etat de prod au 2026-08-24) -> MIGRE vers la forme encadree et corrige au
      passage, exactement comme _strip_legacy_lib() le fait pour la lib heritee ;
    - source vierge -> applique les trois remplacements d'ancrage (diag_leak_replacements),
      ce qui pose un bloc _loadLeakLine deja encadre.

    Termine dans tous les cas par inject_lib(), comme patch_table et patch_diag, pour
    qu'une seule execution suffise a mettre l'appelant (self._loadLeakLine) et
    l'appele (__gasLib.leakWindow) en coherence, sans dependre de l'ordre d'execution
    des scripts patch-*.py."""
    if DIAG_LEAK_BEGIN in controller_script:
        out = _refresh_leak_fetch_block(controller_script)
        return inject_lib(out), ['bloc _loadLeakLine deja marque -> remplace, lib rafraichie']
    if DIAG_LEAK_MARK in controller_script:
        out = _migrate_legacy_leak_block(controller_script)
        return inject_lib(out), [
            'bloc _loadLeakLine legacy (sans marqueurs) -> migre et corrige, lib rafraichie']
    notes = []
    out = controller_script
    for name, old, new in diag_leak_replacements():
        n = out.count(old)
        if n != 1:
            raise AnchorError(f'[{name}] ancre {n}x (attendu 1) -- source live a change')
        out = out.replace(old, new, 1)
        notes.append(f'[{name}] OK (+{len(new) - len(old)}c)')
    out = inject_lib(out)
    notes.append(f'lib injectee ({len(load_gas_lib())} c)')
    return out, notes
