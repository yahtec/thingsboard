"""Tests de validate_decisions (garde-fou du gate reviewed / actions valides)."""
import pytest

import apply_cleanup as ap


def test_rejette_si_non_reviewed():
    with pytest.raises(ValueError, match="reviewed"):
        ap.validate_decisions({"reviewed": False, "dashboards": {}})


def test_rejette_action_inconnue():
    dec = {"reviewed": True, "dashboards": {"d1": {"action": "nuke"}}}
    with pytest.raises(ValueError, match="action"):
        ap.validate_decisions(dec)


def test_accepte_decisions_valides():
    dec = {"reviewed": True, "dashboards": {
        "d1": {"action": "delete", "title": "A"},
        "d2": {"action": "clean", "title": "B", "expected_version": 3, "remove_widgets": ["w"]},
        "d3": {"action": "skip", "title": "C"},
    }}
    ap.validate_decisions(dec)   # ne leve pas


def test_rejette_dashboards_absent():
    with pytest.raises(ValueError, match="dashboards"):
        ap.validate_decisions({"reviewed": True})


def test_rejette_entree_sans_title():
    with pytest.raises(ValueError, match="title"):
        ap.validate_decisions({"reviewed": True, "dashboards": {"d1": {"action": "delete"}}})


def test_rejette_clean_sans_version():
    dec = {"reviewed": True, "dashboards": {"d1": {"action": "clean", "title": "X"}}}
    with pytest.raises(ValueError, match="expected_version"):
        ap.validate_decisions(dec)
