"""I19 : fetches monopage sans detection d'overflow -> risque de doublon a la creation
(find_customer_by_title / find_user_by_email retombent sur une page unique pageSize=500 ;
si le tenant depasse ce seuil, un match existant sur une page suivante est invisible et le
script recree un doublon). Fix : paginer reellement (meme pattern que list_devices_by_profile).

+ M-UUID : http_get(allow_400=True) doit traiter un HTTP 400 (site_customer_id malforme,
UUID invalide cote serveur) comme une absence plutot que d'aborter tout le run — sans
casser le comportement par defaut (allow_400=False) des autres appelants."""
import io
import urllib.error
import urllib.request

import pytest

import _lib_rbac as tb


# ---------- find_customer_by_title : pagination reelle ----------

def test_find_customer_by_title_finds_match_on_second_page(monkeypatch):
    pages = {
        0: {'data': [{'id': {'id': 'c-other'}, 'title': 'Autre'}], 'hasNext': True},
        1: {'data': [{'id': {'id': 'c-target'}, 'title': 'Cible'}], 'hasNext': False},
    }
    calls = []

    def fake_http_get(path, t, allow_404=False, allow_400=False):
        page = 0 if 'page=0' in path else 1
        calls.append(page)
        return pages[page]

    monkeypatch.setattr(tb, 'http_get', fake_http_get)
    c = tb.find_customer_by_title('tok', 'Cible')
    assert c is not None and c['id']['id'] == 'c-target'
    assert calls == [0, 1]  # a bien tourne sur les deux pages


def test_find_customer_by_title_no_match_across_all_pages_returns_none(monkeypatch):
    pages = {
        0: {'data': [{'id': {'id': 'c-1'}, 'title': 'Autre'}], 'hasNext': True},
        1: {'data': [], 'hasNext': False},
    }

    def fake_http_get(path, t, allow_404=False, allow_400=False):
        page = 0 if 'page=0' in path else 1
        return pages[page]

    monkeypatch.setattr(tb, 'http_get', fake_http_get)
    assert tb.find_customer_by_title('tok', 'Introuvable') is None


def test_find_customer_by_title_single_page_backward_compatible(monkeypatch):
    """Non-regression : reponse sans hasNext (vieux mocks de test) ne boucle pas a l'infini."""
    page = {'data': [{'id': {'id': 'c-1'}, 'title': 'X'}]}
    monkeypatch.setattr(tb, 'http_get', lambda p, t, allow_404=False, allow_400=False: page)
    assert tb.find_customer_by_title('tok', 'X')['id']['id'] == 'c-1'


# ---------- find_user_by_email : pagination reelle ----------

def test_find_user_by_email_finds_match_on_second_page(monkeypatch):
    pages = {
        0: {'data': [{'id': {'id': 'u-other'}, 'email': 'other@test.com'}], 'hasNext': True},
        1: {'data': [{'id': {'id': 'u-target'}, 'email': 'Target@Test.com'}], 'hasNext': False},
    }

    def fake_http_get(path, t, allow_404=False, allow_400=False):
        page = 0 if 'page=0' in path else 1
        return pages[page]

    monkeypatch.setattr(tb, 'http_get', fake_http_get)
    u = tb.find_user_by_email('tok', 'target@test.com')
    assert u is not None and u['id']['id'] == 'u-target'


def test_find_user_by_email_no_match_across_all_pages_returns_none(monkeypatch):
    pages = {
        0: {'data': [{'id': {'id': 'u-1'}, 'email': 'a@test.com'}], 'hasNext': True},
        1: {'data': [], 'hasNext': False},
    }

    def fake_http_get(path, t, allow_404=False, allow_400=False):
        page = 0 if 'page=0' in path else 1
        return pages[page]

    monkeypatch.setattr(tb, 'http_get', fake_http_get)
    assert tb.find_user_by_email('tok', 'introuvable@test.com') is None


# ---------- http_get(allow_400=True) : M-UUID ----------

def test_http_get_allow_400_returns_none_instead_of_exit(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, 'Bad Request', {}, io.BytesIO(b'bad uuid'))

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    assert tb.http_get('/api/customer/not-a-uuid', 'tok', allow_400=True) is None


def test_http_get_allow_400_false_still_exits_by_default(monkeypatch):
    """Non-regression : les autres appelants (allow_400 non fourni) gardent le sys.exit dur."""
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 400, 'Bad Request', {}, io.BytesIO(b'bad uuid'))

    monkeypatch.setattr(urllib.request, 'urlopen', fake_urlopen)
    with pytest.raises(SystemExit):
        tb.http_get('/api/customer/not-a-uuid', 'tok')
