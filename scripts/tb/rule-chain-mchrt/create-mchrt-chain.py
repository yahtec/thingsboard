"""Crée la rule chain 'MCHRT Router' (idempotent). Défaut = dry-run ; --apply pour écrire.
Auth via TB_TOKEN (env). Backup non requis (création, pas mutation d'existant)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboards"))
import _lib_tb as tb  # http_get/http_post/token_or_login/BASE_URL
import build_mchrt_chain as B

def find_chain_id(t):
    page = tb.http_get("/api/ruleChains?pageSize=200&page=0&type=CORE", t)
    for rc in page.get("data", []):
        if rc.get("name") == B.CHAIN_NAME:
            return rc["id"]["id"]
    return None

def main():
    apply = "--apply" in sys.argv
    t = tb.token_or_login(os.environ.get("TB_USER"), None)
    existing = find_chain_id(t)
    if existing:
        print(f"[skip] rule chain '{B.CHAIN_NAME}' existe déjà: {existing}")
        print(existing); return
    if not apply:
        print(f"[dry-run] créerait la rule chain '{B.CHAIN_NAME}' + metadata "
              f"({len(B.build_metadata()['nodes'])} nœuds). Relancer avec --apply.")
        return
    rc = tb.http_post("/api/ruleChain", {"name": B.CHAIN_NAME, "type": "CORE",
                                         "debugMode": False, "root": False}, t)
    cid = rc["id"]["id"]
    meta = B.build_metadata()
    meta["ruleChainId"] = {"entityType": "RULE_CHAIN", "id": cid}
    tb.http_post("/api/ruleChain/metadata", meta, t)
    print(f"[applied] rule chain créée: {cid}")
    print(cid)

if __name__ == "__main__":
    main()
