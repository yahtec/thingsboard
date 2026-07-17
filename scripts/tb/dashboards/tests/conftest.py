import sys
from pathlib import Path

# Les scripts dashboards font `import dash_cleanup_lib` / `import _lib_tb` sans inserer
# leur repertoire dans sys.path. En execution directe Python ajoute sys.path[0] ; pas
# quand pytest charge depuis tests/. On insere donc le repertoire parent.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
