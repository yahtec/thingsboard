"""I14 : la migration (chantier #4) supprime volontairement l'attribut `chaufferies`
(CanView-only). Un user migre n'a donc plus cet attribut du tout -> ce n'est PAS un
desaccord, juste une info a skip. Le desaccord ne se declenche que si l'attribut
EXISTE (meme vide) et diverge des CanView."""
import importlib.util
import json
from pathlib import Path

import pytest

RBAC_DIR = Path(__file__).resolve().parents[1]


def _load():
    p = RBAC_DIR / "verify_canview_vs_chaufferies.py"
    spec = importlib.util.spec_from_file_location("verify_canview_vs_chaufferies", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # le script s'auto-insere dans sys.path (ligne 5)
    return mod


mod = _load()
tb = mod.tb

DEVICES_PATH = '/api/tenant/devices?pageSize=1000&page=0&type=pac%20hybride'
USERS_PATH = '/api/users?pageSize=1000&page=0'
DEV1_ATTR_PATH = "/api/plugins/telemetry/DEVICE/dev-1/values/attributes/SERVER_SCOPE?keys=site_customer_id"


def make_responses(user_chaufferies_attr, canview_sites):
    """user_chaufferies_attr : None (absent), ou une liste de device-ids (attribut present).
    canview_sites : liste de site-ids couverts par une relation CanView du party-customer."""
    responses = {
        DEVICES_PATH: {'data': [{'id': {'id': 'dev-1'}, 'name': 'PAC1'}]},
        DEV1_ATTR_PATH: [{'key': 'site_customer_id', 'value': 'site-1'}],
        USERS_PATH: {'data': [{
            'id': {'id': 'user-1'}, 'email': 'party1@test.com',
            'authority': 'CUSTOMER_USER', 'customerId': {'id': 'party-1'},
            'additionalInfo': {},
        }]},
        '/api/plugins/telemetry/USER/user-1/values/attributes/SERVER_SCOPE?keys=chaufferies':
            [] if user_chaufferies_attr is None
            else [{'key': 'chaufferies', 'value': json.dumps(user_chaufferies_attr)}],
        '/api/relations?fromId=party-1&fromType=CUSTOMER':
            [{'type': 'CanView', 'typeGroup': 'COMMON', 'to': {'id': s}} for s in canview_sites],
    }
    return responses


def install(monkeypatch, responses):
    def fake_http_get(path, t, allow_404=False):
        if path not in responses:
            raise AssertionError(f'unexpected GET {path}')
        return responses[path]
    monkeypatch.setenv('TB_TOKEN', 'fake-token')
    monkeypatch.setattr(tb, 'http_get', fake_http_get)
    # Neutralise le backup dashboards (hors-perimetre de ce bug, evite d'ecrire dans le repo).
    monkeypatch.setattr(mod, 'DASHBOARDS', [])


def test_user_without_chaufferies_attr_is_skipped_not_mismatch(monkeypatch, capsys):
    """attribut absent (migre CanView-only) : info + skip, PAS de DESACCORD, exit 0."""
    responses = make_responses(user_chaufferies_attr=None, canview_sites=['site-1'])
    install(monkeypatch, responses)

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'DESACCORD' not in out
    assert 'absent' in out  # message info explicite
    assert exc.value.code == 0


def test_user_with_attribute_diverging_from_canview_is_still_mismatch(monkeypatch, capsys):
    """attribut PRESENT mais divergent des CanView : toujours un vrai DESACCORD, exit 2."""
    responses = make_responses(user_chaufferies_attr=['dev-2'], canview_sites=['site-1'])
    install(monkeypatch, responses)

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'DESACCORD' in out
    assert exc.value.code == 2


def test_user_with_attribute_matching_canview_is_ok(monkeypatch, capsys):
    """Non-regression : attribut present ET aligne avec CanView -> OK, exit 0."""
    responses = make_responses(user_chaufferies_attr=['dev-1'], canview_sites=['site-1'])
    install(monkeypatch, responses)

    with pytest.raises(SystemExit) as exc:
        mod.main()

    out = capsys.readouterr().out
    assert 'DESACCORD' not in out
    assert exc.value.code == 0
