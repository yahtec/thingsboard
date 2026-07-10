"""I18 : ensure_user peut renvoyer CUSTOMER_MISMATCH (email deja utilise sous un autre
customer, customerId immuable cote TB) — provision_portfolio.main() doit le consommer,
le signaler bruyamment et sortir non-zero, SANS masquer le rapport '== Termine =='."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

RBAC_DIR = Path(__file__).resolve().parents[1]


def _load():
    if str(RBAC_DIR) not in sys.path:
        sys.path.insert(0, str(RBAC_DIR))
    p = RBAC_DIR / "provision_portfolio.py"
    spec = importlib.util.spec_from_file_location("provision_portfolio", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()
tb = mod.tb


def _write_cfg(tmp_path, cfg):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg), encoding='utf-8')
    return p


def test_main_reports_customer_mismatch_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    cfg = {
        "sites": [],
        "parties": [{"title": "Party X", "role": "PARTY", "userEmail": "dup@test.com",
                     "canView": []}],
        "staff": [],
    }
    cfg_path = _write_cfg(tmp_path, cfg)

    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['provision_portfolio.py', '--config', str(cfg_path)])

    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-partyx')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user', lambda *a, **k: tb.CUSTOMER_MISMATCH)
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'Termine' in out  # le rapport final n'est pas masque par l'exit non-zero
    assert 'dup@test.com' in out
    assert exc.value.code != 0


def test_main_reports_customer_mismatch_for_staff_too(tmp_path, monkeypatch, capsys):
    cfg = {
        "sites": [],
        "parties": [],
        "staff": [{"title": "Staff X", "role": "STAFF", "userEmail": "dupstaff@test.com",
                   "excluded": []}],
    }
    cfg_path = _write_cfg(tmp_path, cfg)

    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['provision_portfolio.py', '--config', str(cfg_path)])

    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-staffx')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user', lambda *a, **k: tb.CUSTOMER_MISMATCH)
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'Termine' in out
    assert 'dupstaff@test.com' in out
    assert exc.value.code != 0


def test_main_normal_run_no_mismatch_does_not_exit_nonzero(tmp_path, monkeypatch, capsys):
    """Non-regression : un run normal (aucun mismatch) ne doit pas lever SystemExit."""
    cfg = {
        "sites": [],
        "parties": [{"title": "Party OK", "role": "PARTY", "userEmail": "ok@test.com",
                     "canView": []}],
        "staff": [],
    }
    cfg_path = _write_cfg(tmp_path, cfg)

    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['provision_portfolio.py', '--config', str(cfg_path)])

    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-1')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user', lambda *a, **k: 'uid-1')
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])

    mod.main()  # ne doit pas lever SystemExit

    out = capsys.readouterr().out
    assert 'Termine' in out


# ---------- I16 : titre de site inconnu en --apply = erreur dure, pas un [DRY] trompeur ----------

def test_apply_unknown_site_title_canview_is_hard_error_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    cfg = {
        "sites": [],
        "parties": [{"title": "Party X", "role": "PARTY", "userEmail": "px@test.com",
                     "canView": ["Typo Site"]}],
        "staff": [],
    }
    cfg_path = _write_cfg(tmp_path, cfg)
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv',
                         ['provision_portfolio.py', '--config', str(cfg_path), '--apply'])

    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-partyx')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user', lambda *a, **k: 'uid-1')
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])

    def boom(*a, **k):
        raise AssertionError('aucune relation ne doit etre creee pour un site inconnu')

    monkeypatch.setattr(tb, 'ensure_relation', boom)

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'Termine' in out
    assert exc.value.code != 0
    assert 'Typo Site' in out
    assert '[DRY]' not in out  # plus de label trompeur en apply


def test_apply_unknown_site_title_excluded_staff_is_hard_error_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    cfg = {
        "sites": [],
        "parties": [],
        "staff": [{"title": "Staff X", "role": "STAFF", "userEmail": "sx@test.com",
                   "excluded": ["Typo Site"]}],
    }
    cfg_path = _write_cfg(tmp_path, cfg)
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv',
                         ['provision_portfolio.py', '--config', str(cfg_path), '--apply'])

    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-staffx')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user', lambda *a, **k: 'uid-1')
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])

    def boom(*a, **k):
        raise AssertionError('aucune relation ne doit etre creee pour un site inconnu')

    monkeypatch.setattr(tb, 'ensure_relation', boom)

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'Termine' in out
    assert exc.value.code != 0
    assert 'Typo Site' in out
    assert '[DRY]' not in out


def test_apply_unknown_site_and_customer_mismatch_combine_in_single_exit(tmp_path, monkeypatch, capsys):
    """I16 et I18 doivent se combiner dans un seul bloc d'exit non-zero final, sans
    que l'un masque le rapport de l'autre."""
    cfg = {
        "sites": [],
        "parties": [
            {"title": "Party X", "role": "PARTY", "userEmail": "px@test.com",
             "canView": ["Typo Site"]},
            {"title": "Party Dup", "role": "PARTY", "userEmail": "dup@test.com", "canView": []},
        ],
        "staff": [],
    }
    cfg_path = _write_cfg(tmp_path, cfg)
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv',
                         ['provision_portfolio.py', '--config', str(cfg_path), '--apply'])

    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-1')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user',
                         lambda t, email, *a, **k: tb.CUSTOMER_MISMATCH if email == 'dup@test.com' else 'uid-1')
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'Termine' in out
    assert exc.value.code != 0
    assert 'Typo Site' in out
    assert 'dup@test.com' in out


def test_dry_run_unknown_site_title_labeled_clearly_not_misleading(tmp_path, monkeypatch, capsys):
    """En dry-run, le titre inconnu doit rester un simple [DRY] mais avec un libelle qui
    dit clairement qu'il s'agit d'un site inconnu (pas d'un customer 'a creer' normal)."""
    cfg = {
        "sites": [],
        "parties": [{"title": "Party X", "role": "PARTY", "userEmail": "px@test.com",
                     "canView": ["Typo Site"]}],
        "staff": [],
    }
    cfg_path = _write_cfg(tmp_path, cfg)
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['provision_portfolio.py', '--config', str(cfg_path)])

    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-partyx')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user', lambda *a, **k: 'uid-1')
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])

    def boom(*a, **k):
        raise AssertionError('aucune relation ne doit etre creee pour un site inconnu')

    monkeypatch.setattr(tb, 'ensure_relation', boom)

    mod.main()  # dry-run : ne doit pas lever SystemExit

    out = capsys.readouterr().out
    assert 'Typo Site' in out
    assert 'inconnu' in out.lower()


# ---------- I17 : reconciliation site_customer_id (SITES) ----------

def test_sites_reuses_customer_via_site_customer_id_and_notes_title_diff(tmp_path, monkeypatch, capsys):
    cfg = {"sites": [{"title": "Config Title", "device": "PAC1"}], "parties": [], "staff": []}
    cfg_path = _write_cfg(tmp_path, cfg)
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv',
                         ['provision_portfolio.py', '--config', str(cfg_path), '--apply'])

    device = {'id': {'id': 'dev-1'}, 'name': 'PAC1', 'customerId': {'id': 'old-cid'}}
    monkeypatch.setattr(tb, 'find_device_by_name', lambda t, name: device)
    monkeypatch.setattr(tb, 'get_server_attrs',
                         lambda t, et, eid, keys=None: {'site_customer_id': 'real-cid'})
    monkeypatch.setattr(tb, 'http_get',
                         lambda p, t, allow_404=False, allow_400=False:
                         {'id': {'id': 'real-cid'}, 'title': 'Titre reel different'}
                         if 'real-cid' in p else None)

    def boom_ensure_customer(*a, **k):
        raise AssertionError('ne doit pas creer/chercher le customer titre config quand '
                              'site_customer_id existe deja et pointe un customer valide')

    monkeypatch.setattr(tb, 'ensure_customer', boom_ensure_customer)

    calls = []
    monkeypatch.setattr(tb, 'assign_device_to_customer',
                         lambda t, did, cid, apply: calls.append(('assign', cid)))
    monkeypatch.setattr(tb, 'set_server_attribute',
                         lambda t, did, key, value, apply: calls.append(('attr', key, value)))

    mod.main()

    out = capsys.readouterr().out
    assert calls == [('attr', 'site_assigned', True), ('assign', 'real-cid')]
    assert 'Titre reel different' in out  # info : titre config != titre reel du customer reutilise


def test_sites_creates_and_assigns_syncs_site_customer_id_attr_marker_first(tmp_path, monkeypatch, capsys):
    """I17 (sync) + M-ordre (marqueur avant assignation) dans le meme flux : pas de
    site_customer_id existant -> creation via config, assignation, PUIS sync attribut."""
    cfg = {"sites": [{"title": "Config Title", "device": "PAC1"}], "parties": [], "staff": []}
    cfg_path = _write_cfg(tmp_path, cfg)
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv',
                         ['provision_portfolio.py', '--config', str(cfg_path), '--apply'])

    device = {'id': {'id': 'dev-1'}, 'name': 'PAC1', 'customerId': {'id': 'yahtec-cid'}}
    monkeypatch.setattr(tb, 'find_device_by_name', lambda t, name: device)
    monkeypatch.setattr(tb, 'get_server_attrs', lambda t, et, eid, keys=None: {})
    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'new-cid')

    calls = []
    monkeypatch.setattr(tb, 'assign_device_to_customer',
                         lambda t, did, cid, apply: calls.append(('assign', cid)))
    monkeypatch.setattr(tb, 'set_server_attribute',
                         lambda t, did, key, value, apply: calls.append(('attr', key, value)))

    mod.main()

    assert calls == [
        ('attr', 'site_assigned', True),
        ('assign', 'new-cid'),
        ('attr', 'site_customer_id', 'new-cid'),
    ]


def test_sites_device_not_found_still_ensures_customer_for_config_title(tmp_path, monkeypatch, capsys):
    """Non-regression : meme si le device est introuvable, le customer-site du titre
    config doit etre cree/trouve pour que les relations CanView/Excluded en aval marchent."""
    cfg = {"sites": [{"title": "Config Title", "device": "GHOST"}],
           "parties": [{"title": "Party X", "role": "PARTY", "userEmail": "px@test.com",
                        "canView": ["Config Title"]}],
           "staff": []}
    cfg_path = _write_cfg(tmp_path, cfg)
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv',
                         ['provision_portfolio.py', '--config', str(cfg_path), '--apply'])

    monkeypatch.setattr(tb, 'find_device_by_name', lambda t, name: None)
    ensure_customer_calls = []
    monkeypatch.setattr(tb, 'ensure_customer',
                         lambda t, title, apply: ensure_customer_calls.append(title) or 'cid-config')
    monkeypatch.setattr(tb, 'assign_dashboard_to_customer', lambda *a, **k: None)
    monkeypatch.setattr(tb, 'ensure_user', lambda *a, **k: 'uid-1')
    monkeypatch.setattr(tb, 'find_relations_from', lambda *a, **k: [])
    ensure_relation_calls = []
    monkeypatch.setattr(tb, 'ensure_relation',
                         lambda t, cid, sid, rt, apply: ensure_relation_calls.append((cid, sid, rt)))

    mod.main()

    out = capsys.readouterr().out
    assert 'device introuvable' in out
    assert 'Config Title' in ensure_customer_calls
    assert ensure_relation_calls  # la relation CanView a bien pu se creer (sid resolu)


# ---------- M-dry-run : le dry-run des sites doit tout enumerer ----------

def test_sites_dry_run_enumerates_site_assigned_write_for_new_customer(tmp_path, monkeypatch, capsys):
    cfg = {"sites": [{"title": "Config Title", "device": "PAC1"}], "parties": [], "staff": []}
    cfg_path = _write_cfg(tmp_path, cfg)
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['provision_portfolio.py', '--config', str(cfg_path)])  # dry-run

    device = {'id': {'id': 'dev-1'}, 'name': 'PAC1', 'customerId': {}}
    monkeypatch.setattr(tb, 'find_device_by_name', lambda t, name: device)
    monkeypatch.setattr(tb, 'get_server_attrs', lambda t, et, eid, keys=None: {})
    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: None)  # dry-run : pas encore cree

    def boom(*a, **k):
        raise AssertionError('dry-run ne doit rien ecrire')

    monkeypatch.setattr(tb, 'assign_device_to_customer', boom)
    monkeypatch.setattr(tb, 'set_server_attribute', boom)

    mod.main()

    out = capsys.readouterr().out
    assert 'site_assigned' in out
