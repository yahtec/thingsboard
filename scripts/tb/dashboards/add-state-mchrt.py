"""Ajoute les états stub MCHRT au dashboard 'Mes Installations'. Défaut = apply
(+ --dry-run). Backup systématique avant mutation. Auth TB_TOKEN."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import _lib_tb as tb
import mchrt_states_lib as M

def main():
    dry = "--dry-run" in sys.argv
    t = tb.token_or_login(os.environ.get("TB_USER"), None)
    dash = tb.get_dashboard(t)
    tb.backup(dash, "mchrt_states")
    dash["configuration"] = M.add_states(dash["configuration"])
    if dry:
        p = tb.export_json(dash, "preview-mchrt-states.json") if hasattr(tb, "export_json") \
            else None
        print(f"[dry-run] états {M.STATE_APERCU}/{M.STATE_DETAIL} prêts. Preview: {p}")
        return
    tb.post_dashboard(dash, t)
    print(f"[applied] états {M.STATE_APERCU}/{M.STATE_DETAIL} insérés")

if __name__ == "__main__":
    main()
