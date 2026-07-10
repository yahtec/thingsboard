import sys
from pathlib import Path

# migrate_legacy_to_rbac.py fait `import _lib_rbac as tb` sans inserer son propre
# repertoire dans sys.path (ca marche en execution directe car Python ajoute le
# repertoire du script en sys.path[0] ; mais pas quand le module est charge via
# importlib.util depuis un autre repertoire, comme le font ces tests).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
