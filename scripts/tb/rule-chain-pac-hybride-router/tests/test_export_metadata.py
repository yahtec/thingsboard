import importlib.util
from pathlib import Path


def _load():
    p = Path(__file__).resolve().parents[1] / "export-metadata.py"
    spec = importlib.util.spec_from_file_location("export_metadata", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


def test_canonical_json_stable_regardless_of_connection_order():
    m1 = {'nodes': [{'name': 'a'}, {'name': 'b'}],
          'connections': [{'fromIndex': 0, 'toIndex': 1, 'type': 'Success'},
                          {'fromIndex': 1, 'toIndex': 0, 'type': 'Failure'}]}
    m2 = {'nodes': [{'name': 'a'}, {'name': 'b'}],
          'connections': [{'fromIndex': 1, 'toIndex': 0, 'type': 'Failure'},
                          {'fromIndex': 0, 'toIndex': 1, 'type': 'Success'}]}
    assert mod.canonical_json(m1) == mod.canonical_json(m2)


def test_canonical_json_detects_wiring_change():
    m1 = {'nodes': [{'name': 'a'}], 'connections': [{'fromIndex': 0, 'toIndex': 0, 'type': 'True'}]}
    m2 = {'nodes': [{'name': 'a'}], 'connections': [{'fromIndex': 0, 'toIndex': 0, 'type': 'False'}]}
    assert mod.canonical_json(m1) != mod.canonical_json(m2)
