"""Crée le device profile 'mchrt' (idempotent). Défaut dry-run ; --apply pour écrire.
Usage: TB_TOKEN=<jwt> python create_mchrt_profile.py --chain <ruleChainId> [--apply]"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import _lib_rbac as R
import build_mchrt_profile as B

def find_profile(t):
    page = R.http_get("/api/deviceProfileInfos?pageSize=200&page=0", t)
    for p in page.get("data", []):
        if p.get("name") == B.PROFILE_NAME:
            return p["id"]["id"]
    return None

def main():
    apply = "--apply" in sys.argv
    chain = None
    if "--chain" in sys.argv:
        chain = sys.argv[sys.argv.index("--chain") + 1]
    t = R.token_or_login(os.environ.get("TB_USER"), None)
    if find_profile(t):
        print(f"[skip] device profile '{B.PROFILE_NAME}' existe déjà"); return
    if not chain:
        sys.exit("--chain <ruleChainId> requis (uuid de 'MCHRT Router', cf. Task 1)")
    body = B.build(chain)
    if not apply:
        print(f"[dry-run] créerait le profil '{B.PROFILE_NAME}' -> chain {chain}. --apply pour écrire.")
        return
    prof = R.http_post("/api/deviceProfile", body, t)
    print(f"[applied] device profile créé: {prof['id']['id']}")

if __name__ == "__main__":
    main()
