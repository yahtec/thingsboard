"""Tests des helpers reseau/IO ajoutes a _lib_tb.py (monkeypatch pour urllib)."""
import json

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
