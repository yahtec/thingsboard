"""Extension de dash_header_lib.BANNER_IDS aux etats MCHRT (mchrt_apercu/mchrt_detail).
Ne duplique pas la suite existante (test_dash_header_lib.py) ; couvre juste l'ajout."""
import importlib.util
import pathlib

_p = pathlib.Path(__file__).resolve().parents[1] / "dash_header_lib.py"
_s = importlib.util.spec_from_file_location("dash_header_lib", _p)
hdr = importlib.util.module_from_spec(_s)
_s.loader.exec_module(hdr)


def test_mchrt_states_covered():
    assert "mchrt_apercu" in hdr.HEADER_STATES
    assert "mchrt_detail" in hdr.HEADER_STATES


def test_banner_uuids_unique():
    ids = list(hdr.BANNER_IDS.values())
    assert len(ids) == len(set(ids))               # aucun doublon
    assert hdr.BANNER_IDS["mchrt_apercu"] != hdr.BANNER_IDS["mchrt_detail"]


def test_banner_widget_builds_for_mchrt():
    w = hdr.build_banner_widget(hdr.BANNER_IDS["mchrt_apercu"], "alias-123")
    assert w["typeFullFqn"] == "system.cards.markdown_card"


def test_mchrt_banner_ids_valid_uuid():
    import uuid
    uuid.UUID(hdr.BANNER_IDS["mchrt_apercu"])
    uuid.UUID(hdr.BANNER_IDS["mchrt_detail"])
