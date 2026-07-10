"""I5 : sur 401, ne pas readopter le meme JWT mort depuis le cache disque."""
import json
import time

import requests

import common


class FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


def make_client(tmp_path, monkeypatch):
    cache = tmp_path / "jwt.json"
    monkeypatch.setattr(common, "JWT_CACHE", cache)
    c = common.TBClient(url="http://test", user="svc", password="x")
    return c, cache


def test_401_retry_forces_fresh_login_ignores_dead_cache(tmp_path, monkeypatch):
    c, cache = make_client(tmp_path, monkeypatch)
    # Cache disque avec un token "mort" cote serveur mais dont l'exp locale
    # (inventee, now+3600 a l'ecriture) n'est pas encore passee.
    cache.write_text(json.dumps({
        "user": "svc", "token": "dead-token", "exp": time.time() + 3600,
    }))

    login_calls = []

    def fake_post(url, json=None, timeout=None):
        login_calls.append(json)
        return FakeResp(200, {"token": "fresh-token"})

    monkeypatch.setattr(c.s, "post", fake_post)

    request_tokens = []

    def fake_request(method, url, timeout=None, **kw):
        tok = c.s.headers.get("X-Authorization")
        request_tokens.append(tok)
        if tok == "Bearer fresh-token":
            return FakeResp(200, {"ok": True})
        return FakeResp(401)

    monkeypatch.setattr(c.s, "request", fake_request)

    r = c._req("GET", "/api/foo")

    assert r.status_code == 200
    # Un seul login reel a eu lieu (le retry ne doit PAS reutiliser le cache mort).
    assert len(login_calls) == 1
    assert request_tokens == ["Bearer dead-token", "Bearer fresh-token"]
    # Le cache disque contient desormais le token frais, pas le mort.
    assert json.loads(cache.read_text())["token"] == "fresh-token"


def test_valid_cache_skips_login_roundtrip(tmp_path, monkeypatch):
    """Non-regression : un cache valide ne doit PAS declencher de login."""
    c, cache = make_client(tmp_path, monkeypatch)
    cache.write_text(json.dumps({
        "user": "svc", "token": "cached-token", "exp": time.time() + 3600,
    }))

    def fake_post(url, json=None, timeout=None):
        raise AssertionError("no login should happen when disk cache is valid")

    monkeypatch.setattr(c.s, "post", fake_post)

    request_tokens = []

    def fake_request(method, url, timeout=None, **kw):
        request_tokens.append(c.s.headers.get("X-Authorization"))
        return FakeResp(200, {"ok": True})

    monkeypatch.setattr(c.s, "request", fake_request)

    r = c._req("GET", "/api/foo")

    assert r.status_code == 200
    assert request_tokens == ["Bearer cached-token"]
