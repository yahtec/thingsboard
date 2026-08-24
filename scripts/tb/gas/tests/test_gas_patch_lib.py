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
    out, _ = lib.patch_diag(diag_src)
    i = out.index('gas_r290_leak')
    bloc = out[i:i + 2000]
    labels = [s for s in bloc.split("l:'")[1:]]
    for lab in labels[:20]:
        texte = lab.split("'")[0]
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
    assert any('skip' in n for n in notes)


def test_la_lib_injectee_dans_le_diagnostic_est_la_meme(diag_src):
    out, _ = lib.patch_diag(diag_src)
    assert lib.load_gas_lib() in out
