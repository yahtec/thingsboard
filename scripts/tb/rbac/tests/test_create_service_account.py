import importlib.util
from pathlib import Path


def _load():
    p = Path(__file__).resolve().parents[1] / "create_service_account.py"
    spec = importlib.util.spec_from_file_location("create_service_account", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


def test_gen_password_strong_and_random():
    p1, p2 = mod.gen_password(), mod.gen_password()
    assert len(p1) >= 24
    assert p1 != p2  # aléatoire


def test_build_body_tenant_admin_headless():
    b = mod.build_body("svc-tbnotify@yahtec.com")
    assert b["email"] == "svc-tbnotify@yahtec.com"
    assert b["authority"] == "TENANT_ADMIN"
    assert "customerId" not in b            # headless, aucun customer
    assert b["additionalInfo"]["description"]  # documenté
