import re
from pathlib import Path

import pytest

import gas_patch_lib as lib

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def hp_src():
    return (FIXTURES / 'pac_detail_top_wip.live.js').read_text(encoding='utf-8')


@pytest.fixture
def boil_src():
    return (FIXTURES / 'pac_boiler_info.live.js').read_text(encoding='utf-8')


def test_les_ancres_sont_uniques_dans_la_source_live(hp_src, boil_src):
    for name, old, _new in lib.table_replacements('HP'):
        assert hp_src.count(old) == 1, f'ancre {name} introuvable ou multiple'
    for name, old, _new in lib.table_replacements('boil'):
        assert boil_src.count(old) == 1, f'ancre {name} introuvable ou multiple'


def test_le_patch_remplace_le_bloc_par_un_appel_a_la_lib(hp_src):
    out, notes = lib.patch_table(hp_src, 'HP')
    assert "window.__gasLib.rows('R290',hp)" in out
    assert 'hp.conR290!=null?' not in out, 'l ancien bloc conditionnel doit disparaitre'
    assert notes


def test_le_patch_boiler_cible_le_suffixe_g20(boil_src):
    out, _ = lib.patch_table(boil_src, 'boil')
    assert "window.__gasLib.rows('G20',boil)" in out
    assert 'boil.conG20!=null?' not in out


def test_la_lib_est_injectee_en_tete(hp_src):
    out, _ = lib.patch_table(hp_src, 'HP')
    assert out.index(lib.DONE_MARK) < out.index('self.onInit'), \
        'la lib doit preceder le code du widget'


def test_les_deux_widgets_recoivent_une_lib_identique(hp_src, boil_src):
    a, _ = lib.patch_table(hp_src, 'HP')
    b, _ = lib.patch_table(boil_src, 'boil')
    src = lib.load_gas_lib()
    assert src in a and src in b, 'aucune divergence de copie autorisee'


def test_le_patch_est_idempotent(hp_src):
    once, _ = lib.patch_table(hp_src, 'HP')
    twice, notes = lib.patch_table(once, 'HP')
    assert twice == once, 'une seconde application ne doit rien changer'
    assert any('rafraichie' in n for n in notes)


def test_une_ancre_absente_leve_une_erreur():
    with pytest.raises(lib.AnchorError):
        lib.patch_table('self.onInit=function(){};', 'HP')


def test_une_lib_heritee_sans_marqueurs_est_migree(hp_src):
    once, _ = lib.patch_table(hp_src, 'HP')
    legacy = once.replace(lib.LIB_BEGIN + '\n', '', 1).replace(lib.LIB_END + '\n', '', 1)
    assert lib.LIB_BEGIN not in legacy, 'la fixture de depart doit imiter la prod actuelle'
    out, notes = lib.patch_table(legacy, 'HP')
    assert out.count(lib.LIB_BEGIN) == 1, 'un seul bloc, pas de duplication'
    assert lib.load_gas_lib() in out
    assert out.count("window.__gasLib.rows('R290',hp)") == 1, 'les ancres ne sont pas rejouees'
    assert any('migree' in n for n in notes)


def test_la_lib_injectee_est_encadree_par_des_marqueurs(hp_src):
    out, _ = lib.patch_table(hp_src, 'HP')
    assert lib.LIB_BEGIN in out and lib.LIB_END in out
    assert out.index(lib.LIB_BEGIN) < out.index(lib.LIB_END)


def test_une_lib_deja_injectee_est_remplacee_et_non_dupliquee(hp_src):
    once, _ = lib.patch_table(hp_src, 'HP')
    # on simule une evolution de la lib deja injectee
    altere = once.replace('function fmtVer(', 'function fmtVerAncienNom(', 1)
    assert 'fmtVerAncienNom' in altere
    refait = lib.inject_lib(altere)
    assert refait.count(lib.LIB_BEGIN) == 1, 'aucune duplication de bloc'
    assert 'fmtVerAncienNom' not in refait, 'le bloc obsolete doit etre remplace'
    assert lib.load_gas_lib() in refait


def test_inject_lib_ne_mange_pas_le_premier_caractere_sans_saut_de_ligne_apres_lib_end():
    """Bug initial : `controller_script[j + len(LIB_END) + 1:]` supposait exactement un
    caractere (le '\\n' que lib_block() ajoute toujours en sortie) apres le marqueur de
    fin. Une source relue dont LIB_END n'est PAS suivi d'un saut de ligne faisait manger
    le premier caractere du code voisin, en silence."""
    src = lib.LIB_BEGIN + '\nCONTENU_ANCIEN\n' + lib.LIB_END + 'self.onInit=function(){};'
    out = lib.inject_lib(src)
    assert out.endswith('self.onInit=function(){};'), (
        'le premier caractere du code voisin ne doit pas etre mange silencieusement')


def test_widget_start_absent_de_la_lib(hp_src):
    """Invariant dont depend _strip_legacy_lib : si WIDGET_START apparaissait dans
    gas_lib.js, la frontiere de migration heritee deviendrait ambigue (mauvaise
    decoupe silencieuse). Verifie pour lui-meme, pas seulement par ricochet."""
    assert lib.WIDGET_START not in lib.load_gas_lib()


@pytest.fixture
def diag_src():
    return (FIXTURES / 'fault_diagnostic.live.js').read_text(encoding='utf-8')


def test_les_ancres_du_diagnostic_sont_uniques(diag_src):
    for name, old, _new in lib.diag_replacements():
        assert diag_src.count(old) == 1, f'ancre {name} introuvable ou multiple'


def test_le_diagnostic_declare_les_nouvelles_cles(diag_src):
    out, _ = lib.patch_diag(diag_src)
    for k in ('gas_r290_leak', 'gas_g20_leak', 'gas_r290_leak_thr', 'gas_r290_temp',
              'gas_r290_hum', 'gas_r290_fw_ver', 'gas_r290_addr', 'gas_r290_gas_type',
              'gas_r290_life_days', 'gas_r290_life_alarm_thr'):
        assert f'{k} ' in out or f'{k}:' in out, f'cle {k} absente de KEY_META'


def test_les_libelles_gaz_du_diagnostic_restent_ascii(diag_src):
    """Verifie les 26 libelles (13 champs x 2 capteurs) de DIAG_KEY_META, pas
    seulement les 20 premiers : une fenetre tronquee laissait passer les six derniers
    (durees de service en heures, seuils d'avertissement/fin de vie) sans controle.
    Bornage sur lib.DIAG_KEY_META lui-meme (plutot que sur une fenetre de caracteres
    arbitraire dans la sortie complete) pour ne pas deborder sur les libelles d'un
    bloc KEY_META voisin, non soumis a la contrainte ASCII."""
    out, _ = lib.patch_diag(diag_src)
    assert lib.DIAG_KEY_META in out
    labels = [s.split("'")[0] for s in lib.DIAG_KEY_META.split("l:'")[1:]]
    assert len(labels) == 26, 'attendu 13 champs x 2 capteurs'
    for texte in labels:
        assert texte.isascii(), f'libelle non ASCII dans le bloc gaz : {texte}'


def test_le_diagnostic_route_les_formateurs_vers_la_lib(diag_src):
    out, _ = lib.patch_diag(diag_src)
    assert "m.f==='ver'" in out
    assert "m.f==='errbits'" in out
    assert 'window.__gasLib.fmtVer(v)' in out
    assert 'window.__gasLib.decodeErr(v)' in out


def test_le_diagnostic_marque_les_registres_de_defaut(diag_src):
    out, _ = lib.patch_diag(diag_src)
    assert "gas_r290_err :{l:'Defaut capteur R290 (registre)',u:'',s:1,d:0,f:'errbits'}" in out


def test_le_diagnostic_enumere_alarme_et_mode(diag_src):
    out, _ = lib.patch_diag(diag_src)
    assert "gas_r290_leak:{0:'non',1:'oui'}" in out
    assert "gas_r290_op_mode:{0:'démarrage',1:'mesure'}" in out


def test_le_patch_diagnostic_est_idempotent(diag_src):
    once, _ = lib.patch_diag(diag_src)
    twice, notes = lib.patch_diag(once)
    assert twice == once
    assert any('rafraichie' in n for n in notes)


def test_la_lib_injectee_dans_le_diagnostic_est_la_meme(diag_src):
    out, _ = lib.patch_diag(diag_src)
    assert lib.load_gas_lib() in out


# ---------- ligne "alarme capteur" (amendement 2026-08-24, remplace le widget timeline) ----------

def test_les_ancres_de_la_ligne_alarme_capteur_sont_uniques(diag_src):
    for name, old, _new in lib.diag_leak_replacements():
        assert diag_src.count(old) == 1, f'ancre {name} introuvable ou multiple'


def test_l_ancre_de_declenchement_reste_unique_malgre_plusieurs_var_c_self_ctx(diag_src):
    """`var c = self._ctx;` apparait a plusieurs endroits du fichier (_renderHeader,
    _fetchRealtime, et un troisieme site) : seule l'ancre elargie a la signature
    self._renderHeader = function(){ est fiable pour cibler le declenchement."""
    assert diag_src.count('var c = self._ctx;') > 1, (
        'la fixture doit contenir plusieurs occurrences pour que ce test ait un sens')
    _, old, _new = [r for r in lib.diag_leak_replacements()
                    if 'declenchement' in r[0]][0]
    assert diag_src.count(old) == 1


def test_le_patch_leak_line_ajoute_la_ligne_de_rendu(diag_src):
    out, _ = lib.patch_diag_leak(diag_src)
    assert "self._leakLine ? \"<div class='when'>\"+self._leakLine+\"</div>\"" in out


def test_le_patch_leak_line_ajoute_le_chargement_paresseux(diag_src):
    out, _ = lib.patch_diag_leak(diag_src)
    assert 'self._loadLeakLine = function(){' in out
    assert 'window.__gasLib.leakWindow(hist, p[1], 1)' in out
    assert out.index('self._loadLeakLine = function(){') < out.index(
        'self._fetchRealtime = function(){'), 'le chargement doit preceder _fetchRealtime'


def test_le_patch_leak_line_declenche_depuis_renderheader(diag_src):
    out, _ = lib.patch_diag_leak(diag_src)
    assert 'self._renderHeader = function(){\n    var c = self._ctx;\n    self._loadLeakLine();' in out


def test_le_patch_leak_line_est_idempotent(diag_src):
    once, _ = lib.patch_diag_leak(diag_src)
    twice, notes = lib.patch_diag_leak(once)
    assert twice == once
    assert any('deja' in n for n in notes)


def test_une_ancre_absente_de_la_ligne_alarme_capteur_leve_une_erreur():
    with pytest.raises(lib.AnchorError):
        lib.patch_diag_leak('self._renderHeader = function(){};')


def _leak_block_body(js):
    """Contenu du bloc _loadLeakLine encadre (entre DIAG_LEAK_BEGIN et DIAG_LEAK_END),
    marqueurs exclus. Sert a isoler les assertions sur probeTs : la meme sous-chaine
    (ordre evtResolvedTs d'abord) apparait LEGITIMEMENT ailleurs dans le widget, dans
    _fetchRealtime, ou ce choix est correct -- chercher dans la source complete
    donnerait de faux positifs/negatifs sans rapport avec le bloc teste ici."""
    i = js.index(lib.DIAG_LEAK_BEGIN)
    j = js.index(lib.DIAG_LEAK_END, i)
    return js[i:j]


# ---------- bloc _loadLeakLine remplacable (correction du defaut d'ancrage 2026-08-24) ----
# Le defaut de prod : un bloc deja insere (DIAG_LEAK_MARK present) faisait prendre a
# patch_diag_leak() la branche "deja en place", qui rafraichissait la lib mais ne
# rejouait jamais _DIAG_LEAK_FETCH_CONTENT -- aucune correction du bloc ne pouvait donc
# atteindre un widget deja patche. Les quatre tests ci-dessous verifient le mecanisme
# de remplacement introduit pour lever ce blocage : un bloc deja encadre est remplace
# (pas ignore), un bloc insere avant les marqueurs est reconnu et migre, aucun des deux
# chemins ne duplique le bloc, et l'ensemble reste idempotent.

def test_la_fenetre_alarme_capteur_est_ancree_sur_evtts_pas_evtresolvedts(diag_src):
    """Le defaut lui-meme (point 1) : la fenetre doit etre centree sur l'apparition du
    defaut (c.evtTs), pas sur sa resolution (c.evtResolvedTs) -- contrairement a
    _fetchRealtime, ou ce choix est legitime. Preuve relevee en base : un defaut gaz
    apparu le 08/08 a 12:23:30 et resolu 16 jours plus tard (24/08 10:28:20)."""
    out, _ = lib.patch_diag_leak(diag_src)
    bloc = _leak_block_body(out)
    assert 'var probeTs = (c.evtTs && c.evtTs > 0) ? c.evtTs : c.evtResolvedTs;' in bloc
    assert 'var probeTs = (c.evtResolvedTs && c.evtResolvedTs > 0) ? c.evtResolvedTs : c.evtTs;' \
        not in bloc, 'ancienne priorite (resolution avant apparition) : ne doit plus apparaitre'


def test_le_bloc_loadleakline_est_encadre_par_des_marqueurs(diag_src):
    out, _ = lib.patch_diag_leak(diag_src)
    assert lib.DIAG_LEAK_BEGIN in out and lib.DIAG_LEAK_END in out
    assert out.index(lib.DIAG_LEAK_BEGIN) < out.index('self._loadLeakLine = function(){') < \
        out.index(lib.DIAG_LEAK_END) < out.index('self._fetchRealtime = function(){')


def test_un_bloc_loadleakline_deja_marque_est_remplace_sans_duplication(diag_src):
    """Simule une correction future du bloc : on altere le contenu deja encadre (comme
    le ferait un vieux deploiement portant encore le defaut d'ancrage) puis on
    reapplique le patch. Le bloc altere doit disparaitre, remplace par la version
    courante -- pas conserve au pretexte que DIAG_LEAK_MARK est deja present."""
    once, _ = lib.patch_diag_leak(diag_src)
    altere = once.replace(
        'var probeTs = (c.evtTs && c.evtTs > 0) ? c.evtTs : c.evtResolvedTs;',
        'var probeTs = (c.evtResolvedTs && c.evtResolvedTs > 0) ? c.evtResolvedTs : c.evtTs;', 1)
    assert 'evtResolvedTs && c.evtResolvedTs > 0' in altere, 'la simulation doit avoir pris effet'
    refait, notes = lib.patch_diag_leak(altere)
    assert refait.count(lib.DIAG_LEAK_BEGIN) == 1, 'aucune duplication de bloc'
    assert refait.count(lib.DIAG_LEAK_END) == 1
    assert refait.count('self._loadLeakLine = function(){') == 1
    bloc = _leak_block_body(refait)
    assert 'evtResolvedTs && c.evtResolvedTs > 0' not in bloc, 'le bloc altere doit etre remplace'
    assert 'var probeTs = (c.evtTs && c.evtTs > 0) ? c.evtTs : c.evtResolvedTs;' in bloc
    assert any('remplace' in n for n in notes)


def test_un_bloc_loadleakline_non_encadre_en_prod_est_migre_et_corrige(diag_src):
    """Simule l'etat REEL de prod au 2026-08-24 : le bloc _loadLeakLine a ete insere par
    une version anterieure de ce script, SANS marqueurs, et porte encore le defaut
    d'ancrage (probeTs teste evtResolvedTs en premier). La migration doit reconnaitre
    ce bloc a partir de DIAG_LEAK_LEGACY_START (et non DIAG_LEAK_BEGIN, absent), le
    remplacer par la version courante et l'encadrer -- exactement comme
    _strip_legacy_lib() le fait pour la lib heritee. Sans ce chemin, la correction du
    defaut d'ancrage resterait bloquee en local (elle ne pourrait jamais atteindre la
    prod, deja patchee sans marqueurs)."""
    once, _ = lib.patch_diag_leak(diag_src)
    legacy = once.replace(lib.DIAG_LEAK_BEGIN + '\n', '', 1).replace(
        '\n' + lib.DIAG_LEAK_END, '', 1)
    legacy = legacy.replace(
        'var probeTs = (c.evtTs && c.evtTs > 0) ? c.evtTs : c.evtResolvedTs;',
        'var probeTs = (c.evtResolvedTs && c.evtResolvedTs > 0) ? c.evtResolvedTs : c.evtTs;', 1)
    assert lib.DIAG_LEAK_BEGIN not in legacy, 'la fixture de depart doit imiter la prod actuelle'
    assert lib.DIAG_LEAK_MARK in legacy, 'le bloc legacy doit rester detectable comme deja insere'
    migre, notes = lib.patch_diag_leak(legacy)
    assert migre.count(lib.DIAG_LEAK_BEGIN) == 1, 'un seul bloc, pas de duplication'
    assert migre.count(lib.DIAG_LEAK_END) == 1
    assert migre.count('self._loadLeakLine = function(){') == 1
    bloc = _leak_block_body(migre)
    assert 'var probeTs = (c.evtTs && c.evtTs > 0) ? c.evtTs : c.evtResolvedTs;' in bloc, \
        'la migration doit corriger le defaut d ancrage, pas seulement encadrer le bloc'
    assert 'evtResolvedTs && c.evtResolvedTs > 0' not in bloc
    assert any('migre' in n for n in notes)


def test_le_remplacement_et_la_migration_du_bloc_loadleakline_restent_idempotents(diag_src):
    once, _ = lib.patch_diag_leak(diag_src)
    twice, notes_deux = lib.patch_diag_leak(once)
    thrice, notes_trois = lib.patch_diag_leak(twice)
    assert twice == once == thrice
    assert any('deja' in n for n in notes_deux)
    assert any('deja' in n for n in notes_trois)


# ---------- coherence appelant / appele avec _src/gas_lib.js ----------
# Le defaut constate en prod le 2026-08-24 : un commit a ajoute leakWindow() a
# gas_lib.js et un script a ecrit un appel a window.__gasLib.leakWindow(...) dans
# tduo.fault_diagnostic, mais la lib deployee n'avait jamais ete rafraichie -- la
# fonction appelee n'existait pas en prod, en silence (le .catch() masquait tout).
# Les tests ci-dessous relevent, par expression reguliere, les noms REELLEMENT
# appeles dans le resultat des fonctions de patch, et les comparent aux noms
# REELLEMENT exportes par root.__gasLib dans _src/gas_lib.js -- jamais un texte
# recopie a la main -- pour qu'un futur ajout d'appel a une fonction absente (ou un
# renommage cote lib non repercute) echoue ici plutot qu'en production.

_GASLIB_CALL_RE = re.compile(r'__gasLib\.(\w+)\(')


def _lib_export_names():
    """Noms exportes par root.__gasLib = { ... } dans _src/gas_lib.js, extraits par
    regex sur le fichier source lui-meme (pas une liste recopiee a la main)."""
    src = lib.load_gas_lib()
    m = re.search(r'root\.__gasLib\s*=\s*\{(.*?)\};', src, re.S)
    assert m, 'bloc `root.__gasLib = {...}` introuvable dans _src/gas_lib.js'
    noms = set(re.findall(r'(\w+)\s*:', m.group(1)))
    assert noms, 'regex export : aucun nom trouve -- verifier le format de gas_lib.js'
    return noms


@pytest.fixture
def patched_sources(hp_src, boil_src, diag_src):
    """Sortie des trois fonctions de patch appliquees aux fixtures live -- les memes
    sources que celles postees en production par les enveloppes REST patch-*.py."""
    return {
        "patch_table('HP')": lib.patch_table(hp_src, 'HP')[0],
        "patch_table('boil')": lib.patch_table(boil_src, 'boil')[0],
        'patch_diag': lib.patch_diag(diag_src)[0],
        'patch_diag_leak': lib.patch_diag_leak(diag_src)[0],
    }


def test_tous_les_appels_a_gaslib_correspondent_a_un_export_de_la_lib(patched_sources):
    exports = _lib_export_names()
    vus = set()
    for label, js in patched_sources.items():
        appeles = set(_GASLIB_CALL_RE.findall(js))
        assert appeles, f'{label} : aucun appel __gasLib.*( detecte -- regex a verifier'
        vus |= appeles
        manquants = appeles - exports
        assert not manquants, (
            f"{label} appelle __gasLib.{sorted(manquants)}, absent des exports de "
            "_src/gas_lib.js")
    # Garde-fou du test lui-meme : s'assurer qu'on couvre bien plusieurs fonctions de
    # la lib, pas seulement une, sans quoi le test serait trivialement peu utile.
    assert len(vus) >= 3, f'couverture trop faible, seulement {sorted(vus)} appeles'


def _settings_live():
    """Forme relevee en production le 2026-07-31."""
    return {'title': 'Gaz / Sécurité', 'series': [
        {'unit': '%LFL', 'color': '#ff6f00', 'field': 'HP.conR290',
         'label': 'Conc. R290', 'scale': 0.1},
        {'unit': '%LFL', 'color': '#00acc1', 'field': 'boil.conG20',
         'label': 'Conc. G20', 'scale': 0.1},
    ]}


def test_les_deux_series_de_seuil_sont_ajoutees():
    out, note = lib.add_threshold_series(_settings_live())
    champs = [s['field'] for s in out['series']]
    assert champs == ['HP.conR290', 'boil.conG20',
                     'HP.leakThresR290', 'boil.leakThresG20']
    assert note


def test_les_series_existantes_ne_sont_pas_touchees():
    avant = _settings_live()
    out, _ = lib.add_threshold_series(avant)
    assert out['series'][0] == {'unit': '%LFL', 'color': '#ff6f00',
                               'field': 'HP.conR290', 'label': 'Conc. R290', 'scale': 0.1}
    assert out['title'] == 'Gaz / Sécurité'


def test_la_serie_de_seuil_porte_la_meme_echelle_que_la_mesure():
    out, _ = lib.add_threshold_series(_settings_live())
    seuil = [s for s in out['series'] if s['field'] == 'HP.leakThresR290'][0]
    assert seuil['scale'] == 0.1, 'sinon le seuil ne serait pas comparable a la mesure'
    assert seuil['unit'] == '%LFL'


def test_l_ajout_du_seuil_est_idempotent():
    once, _ = lib.add_threshold_series(_settings_live())
    twice, note = lib.add_threshold_series(once)
    assert twice == once
    assert 'skip' in note


def test_une_serie_de_seuil_divergente_est_ramenee_a_la_forme_canonique():
    settings = _settings_live()
    settings['series'].append(
        {'field': 'HP.leakThresR290', 'label': 'Seuil R290', 'unit': '%LFL',
         'scale': 1, 'color': '#9e9e9e'})
    out, note = lib.add_threshold_series(settings)
    seuil = [s for s in out['series'] if s['field'] == 'HP.leakThresR290'][0]
    assert seuil['scale'] == 0.1, 'la serie divergente doit etre ramenee a la forme canonique'
    assert 'corrigees' in note


def test_les_dicts_de_series_ne_sont_pas_partages_avec_l_entree():
    avant = _settings_live()
    out, _ = lib.add_threshold_series(avant)
    assert out['series'][0] is not avant['series'][0], \
        'la sortie ne doit pas partager les dicts de series de l entree'


def test_quand_tout_est_conforme_l_objet_recu_est_renvoye_tel_quel():
    once, _ = lib.add_threshold_series(_settings_live())
    twice, note = lib.add_threshold_series(once)
    assert twice is once, 'contrat sur lequel s appuyait le script : identite preservee au skip'
    assert 'skip' in note


# Les tests de lib.LANES, de la lib encadree du controleur timeline et du bootstrap
# PD() partage avec tsmart.pac_chart ont ete retires avec le widget lui-meme
# (amendement du 2026-08-24) : la fonction de construction des pistes n'a plus
# d'appelant, et gas-registers.controller.js/.html/.css ainsi que
# tests/fixtures/pac_chart.live.js ont disparu.
