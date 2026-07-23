"""Applique la bascule PAC|MCHRT au dashboard. Défaut apply (+ --dry-run). Backup avant.
Auth TB_TOKEN."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import _lib_tb as tb
import menu_toggle_lib as M

def main():
    dry = "--dry-run" in sys.argv
    t = tb.token_or_login(os.environ.get("TB_USER"), None)
    dash = tb.get_dashboard(t)
    tb.backup(dash, "mchrt_menu_toggle")
    dash["configuration"] = M.apply(dash["configuration"])
    if dry:
        print("[dry-run] bascule prête (marqueur __MCHRT_MENU_V1__). Backup écrit.")
        return
    tb.post_dashboard(dash, t)
    print("[applied] bascule PAC|MCHRT posée")

if __name__ == "__main__":
    main()
