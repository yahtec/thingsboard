"""M-collision : avant de reutiliser un customer trouve par TITRE (pas par
site_customer_id), verifier qu'il n'est pas etranger (party-customer d'un intervenant,
prefixe 'Party — ', ou porteur d'users) -> sinon suffixer le titre et avertir plutot que
de reutiliser silencieusement un customer qui n'appartient pas a l'onboarding de sites.

M-UUID : un site_customer_id corrompu (non-UUID / 400 cote TB) doit etre traite comme
absent (warning + poursuite normale), pas provoquer l'abort de tout le run.

Compteurs : `created` ne doit compter que les VRAIES creations, pas les reutilisations
par titre (cosmetique, mais verifie ici)."""
import importlib.util
import sys
from pathlib import Path

import pytest

RBAC_DIR = Path(__file__).resolve().parents[1]


def _load():
    if str(RBAC_DIR) not in sys.path:
        sys.path.insert(0, str(RBAC_DIR))
    p = RBAC_DIR / "onboard_sites.py"
    spec = importlib.util.spec_from_file_location("onboard_sites", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()
tb = mod.tb


def _device(did='dev-1', name='PAC1'):
    return {'id': {'id': did}, 'name': name, 'type': 'pac hybride'}


def _base_patches(monkeypatch, devices, server_attrs_by_device=None, http_get_map=None):
    server_attrs_by_device = server_attrs_by_device or {}
    http_get_map = http_get_map or {}

    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(sys, 'argv', ['onboard_sites.py'])  # dry-run par defaut, sauf override
    monkeypatch.setattr(tb, 'list_devices_by_profile', lambda t, profile: devices)

    def fake_get_server_attrs(t, entity_type, entity_id, keys=None):
        return server_attrs_by_device.get(entity_id, {})

    def fake_http_get(path, t, allow_404=False, allow_400=False):
        return http_get_map.get(path)

    monkeypatch.setattr(tb, 'get_server_attrs', fake_get_server_attrs)
    monkeypatch.setattr(tb, 'http_get', fake_http_get)
    return server_attrs_by_device, http_get_map


# ---------- M-collision ----------

def test_foreign_party_customer_prefixed_is_not_reused_title_is_suffixed(monkeypatch, capsys):
    devices = [_device()]
    _base_patches(monkeypatch, devices, server_attrs_by_device={
        'dev-1': {'nom_residence': 'MaResidence'},
    })
    # customer trouve par titre "MaResidence" = un party-customer d'intervenant (etranger)
    foreign = {'id': {'id': 'cid-party'}, 'title': 'MaResidence'}
    monkeypatch.setattr(tb, 'find_customer_by_title',
                         lambda t, title: foreign if title == 'MaResidence' else None)

    ensure_customer_titles = []

    def fake_ensure_customer(t, title, apply):
        ensure_customer_titles.append(title)
        return None  # dry-run

    monkeypatch.setattr(tb, 'ensure_customer', fake_ensure_customer)
    # marquer le customer trouve comme "Party — " pour simuler l'etrangete par prefixe
    foreign['title'] = 'Party — quelqu-un@test.com'

    def fake_find_customer_by_title(t, title):
        if title == 'MaResidence':
            return foreign
        return None

    monkeypatch.setattr(tb, 'find_customer_by_title', fake_find_customer_by_title)

    mod.main()

    out = capsys.readouterr().out
    assert 'collision' in out.lower()
    # le titre finalement utilise pour ensure_customer ne doit PAS etre le titre brut
    # collisionne (sinon on retomberait sur le meme party-customer etranger)
    assert ensure_customer_titles and ensure_customer_titles[0] != 'MaResidence'


def test_foreign_customer_with_users_is_not_reused(monkeypatch, capsys):
    devices = [_device()]
    _base_patches(monkeypatch, devices, server_attrs_by_device={
        'dev-1': {'nom_residence': 'SiteHomonyme'},
    })
    found = {'id': {'id': 'cid-foreign'}, 'title': 'SiteHomonyme'}

    def fake_http_get(path, t, allow_404=False, allow_400=False):
        if 'users' in path:
            return {'data': [{'id': {'id': 'u-1'}}]}  # ce customer a des users attaches
        return None

    monkeypatch.setattr(tb, 'http_get', fake_http_get)
    monkeypatch.setattr(tb, 'find_customer_by_title', lambda t, title: found)

    ensure_customer_titles = []
    monkeypatch.setattr(tb, 'ensure_customer',
                         lambda t, title, apply: ensure_customer_titles.append(title) or None)

    mod.main()

    out = capsys.readouterr().out
    assert 'collision' in out.lower()
    assert ensure_customer_titles and ensure_customer_titles[0] != 'SiteHomonyme'


def test_non_foreign_customer_by_title_is_reused_normally(monkeypatch, capsys):
    """Non-regression : un customer trouve par titre, SANS users et sans prefixe 'Party —
    ', est un vrai site-customer d'onboarding -> reutilisation normale (pas de suffixe)."""
    devices = [_device()]
    _base_patches(monkeypatch, devices, server_attrs_by_device={
        'dev-1': {'nom_residence': 'SiteOK'},
    })
    found = {'id': {'id': 'cid-ok'}, 'title': 'SiteOK'}

    def fake_http_get(path, t, allow_404=False, allow_400=False):
        if 'users' in path:
            return {'data': []}  # pas d'user attache
        return None

    monkeypatch.setattr(tb, 'http_get', fake_http_get)
    monkeypatch.setattr(tb, 'find_customer_by_title', lambda t, title: found)

    ensure_customer_titles = []
    monkeypatch.setattr(tb, 'ensure_customer',
                         lambda t, title, apply: ensure_customer_titles.append(title) or 'cid-ok')

    mod.main()

    out = capsys.readouterr().out
    assert 'collision' not in out.lower()
    assert ensure_customer_titles == ['SiteOK']


# ---------- M-UUID ----------

def test_malformed_site_customer_id_is_warned_and_treated_as_absent(monkeypatch, capsys):
    devices = [_device()]
    _base_patches(monkeypatch, devices, server_attrs_by_device={
        'dev-1': {'nom_residence': 'SiteX', 'site_customer_id': 'not-a-uuid'},
    })

    def fake_http_get(path, t, allow_404=False, allow_400=False):
        if path.startswith('/api/customer/not-a-uuid'):
            assert allow_400 is True  # M-UUID : le 400 doit etre absorbe, pas aborter
            return None
        if 'users' in path:
            return {'data': []}
        return None

    monkeypatch.setattr(tb, 'http_get', fake_http_get)
    monkeypatch.setattr(tb, 'find_customer_by_title', lambda t, title: None)
    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: None)

    mod.main()  # ne doit PAS lever SystemExit / aborter

    out = capsys.readouterr().out
    assert 'not-a-uuid' in out
    assert 'invalide' in out.lower() or 'malform' in out.lower()


def test_valid_site_customer_id_is_reused_and_counted(monkeypatch, capsys):
    devices = [_device()]
    _base_patches(monkeypatch, devices, server_attrs_by_device={
        'dev-1': {'nom_residence': 'SiteY', 'site_customer_id': 'cid-existing'},
    })

    def fake_http_get(path, t, allow_404=False, allow_400=False):
        if path.startswith('/api/customer/cid-existing'):
            return {'id': {'id': 'cid-existing'}, 'title': 'SiteY'}
        return None

    monkeypatch.setattr(tb, 'http_get', fake_http_get)

    def boom(*a, **k):
        raise AssertionError('pas de creation attendue : reuse via site_customer_id')

    monkeypatch.setattr(tb, 'ensure_customer', boom)

    mod.main()

    out = capsys.readouterr().out
    assert 'REUSE' in out
    assert 'reuse=1' in out
    assert 'cree/maj=0' in out


# ---------- created vs reused (cosmetique) ----------

def test_created_counter_does_not_count_reuse_by_title(monkeypatch, capsys):
    devices = [_device()]
    _base_patches(monkeypatch, devices, server_attrs_by_device={
        'dev-1': {'nom_residence': 'SiteReuseByTitle'},
    })
    found = {'id': {'id': 'cid-existing-title'}, 'title': 'SiteReuseByTitle'}

    def fake_http_get(path, t, allow_404=False, allow_400=False):
        if 'users' in path:
            return {'data': []}
        return None

    monkeypatch.setattr(tb, 'http_get', fake_http_get)
    monkeypatch.setattr(tb, 'find_customer_by_title', lambda t, title: found)
    monkeypatch.setattr(sys, 'argv', ['onboard_sites.py', '--apply'])
    monkeypatch.setattr(tb, 'ensure_customer', lambda t, title, apply: 'cid-existing-title')
    monkeypatch.setattr(tb, 'set_server_attribute', lambda *a, **k: None)

    mod.main()

    out = capsys.readouterr().out
    assert 'cree/maj=0' in out
    assert 'reuse=1' in out
