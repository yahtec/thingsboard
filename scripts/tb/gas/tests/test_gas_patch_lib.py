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
    assert any('skip' in n for n in notes)


def test_une_ancre_absente_leve_une_erreur():
    with pytest.raises(lib.AnchorError):
        lib.patch_table('self.onInit=function(){};', 'HP')
