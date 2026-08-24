"""Tests des helpers reseau/IO ajoutes a _lib_tb.py (monkeypatch pour urllib)."""
import json

import pytest

import _lib_tb as tb


def test_export_json_round_trips(tmp_path):
    p = tmp_path / "sub" / "dash.json"      # le sous-dossier n'existe pas encore
    obj = {"title": "é à", "n": 1}
    ret = tb.export_json(obj, str(p))
    assert ret == str(p) and p.exists()
    assert json.loads(p.read_text(encoding="utf-8")) == obj


def test_token_from_file_strips(tmp_path):
    p = tmp_path / "tok.txt"
    p.write_text("  abc.def.ghi \n", encoding="utf-8")
    assert tb.token_from_file(str(p)) == "abc.def.ghi"


def test_list_tenant_dashboards_depagine(monkeypatch):
    pages = {
        0: {"data": [{"id": {"id": "d1"}}, {"id": {"id": "d2"}}], "hasNext": True},
        1: {"data": [{"id": {"id": "d3"}}], "hasNext": False},
    }

    def fake_get(path, t):
        page = int(path.split("page=")[1])
        return pages[page]

    monkeypatch.setattr(tb, "http_get", fake_get)
    out = tb.list_tenant_dashboards("tok")
    assert [d["id"]["id"] for d in out] == ["d1", "d2", "d3"]


# ---------- token_or_login : ordre de priorite TB_TOKEN > --pwd > TB_USER+TB_PASS ----------
# Ajoute avec la lecture des identifiants sur le serveur (creds-from-server.sh, voir
# scripts/tb/gas) : le compte de service svc-tbnotify@yahtec.com est expose via
# TB_USER/TB_PASS dans l'environnement, jamais en argument de ligne de commande.

def test_token_or_login_tb_token_prioritaire_sur_tout(monkeypatch):
    calls = []
    monkeypatch.setattr(tb, "login", lambda u, p: calls.append((u, p)) or f"tok-{u}")
    monkeypatch.setenv("TB_TOKEN", "jeton-depuis-env")
    monkeypatch.setenv("TB_USER", "svc-tbnotify@yahtec.com")
    monkeypatch.setenv("TB_PASS", "secret-env")
    assert tb.token_or_login("je@yahtec.com", "mdp-cli") == "jeton-depuis-env"
    assert calls == [], "TB_TOKEN present : login() ne doit jamais etre appele"


def test_token_or_login_pwd_prioritaire_sur_env_user_pass(monkeypatch):
    calls = []
    monkeypatch.setattr(tb, "login", lambda u, p: calls.append((u, p)) or f"tok-{u}")
    monkeypatch.delenv("TB_TOKEN", raising=False)
    monkeypatch.setenv("TB_USER", "svc-tbnotify@yahtec.com")
    monkeypatch.setenv("TB_PASS", "secret-env")
    assert tb.token_or_login("je@yahtec.com", "mdp-cli") == "tok-je@yahtec.com"
    assert calls == [("je@yahtec.com", "mdp-cli")], "--pwd doit passer avant TB_USER/TB_PASS"


def test_token_or_login_bascule_sur_tb_user_pass_sans_token_ni_pwd(monkeypatch):
    calls = []
    monkeypatch.setattr(tb, "login", lambda u, p: calls.append((u, p)) or f"tok-{u}")
    monkeypatch.delenv("TB_TOKEN", raising=False)
    monkeypatch.setenv("TB_USER", "svc-tbnotify@yahtec.com")
    monkeypatch.setenv("TB_PASS", "secret-env")
    assert tb.token_or_login("je@yahtec.com", None) == "tok-svc-tbnotify@yahtec.com"
    assert calls == [("svc-tbnotify@yahtec.com", "secret-env")], (
        "sans TB_TOKEN ni --pwd, la connexion doit utiliser TB_USER/TB_PASS (env), pas "
        "le --user recu en argument")


def test_token_or_login_echoue_sans_aucun_identifiant(monkeypatch):
    monkeypatch.delenv("TB_TOKEN", raising=False)
    monkeypatch.delenv("TB_USER", raising=False)
    monkeypatch.delenv("TB_PASS", raising=False)
    with pytest.raises(SystemExit):
        tb.token_or_login("je@yahtec.com", None)
