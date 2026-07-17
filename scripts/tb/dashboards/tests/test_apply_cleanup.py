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
        "d1": {"action": "delete"},
        "d2": {"action": "clean", "expected_version": 3, "remove_widgets": ["w"]},
        "d3": {"action": "skip"},
    }}
    ap.validate_decisions(dec)   # ne leve pas
