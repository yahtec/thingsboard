"""Appariement apparition/resolution des evenements evt_* (common.pair_events).

Cette fonction n'avait aucun test direct — elle n'etait exercee qu'indirectement
par les tests des deux crons. C'est pourtant elle qui a produit un defaut
fantome en production le 2026-08-31 : `open_by_key` ne gardait qu'UNE apparition
ouverte par cle, donc une reapparition avant resolution ecrasait la precedente,
et la resolution ne fermait que la derniere. La premiere restait ouverte pour
toujours, dans le recap ET dans l'historique du dashboard (dont le JS reproduit
cette fonction a l'identique).

Cas reel : device 2623001001, defaut 112 (Gaz G20 detecte) / sous-equipement 50,
apparitions a 07:15:46 et 07:27:46, resolution unique a 08:35:42. Trois jours
plus tard la premiere apparition etait toujours affichee active.
"""
import common

MIN = 60_000
T = 1_788_000_000_000


def _rec(ts, typ, fault=15, dev=50):
    """Un enregistrement evt_* tel que `collect_records` le produit."""
    return {
        "ts": ts,
        "evt_type": typ,
        "evt_fault": fault,
        "evt_device": dev,
        "evt_status": 1 if typ == 1 else 0,
        "evt_id": ts // 1000,
        "evt_date": "31/08/26",
        "evt_time": "10:00:00",
        "fault_src": 0,
    }


# ── Le bug : reapparition avant resolution ──────────────────────────────────

def test_deux_apparitions_une_resolution_ferme_les_deux():
    """Le cas exact du fantome de production. La resolution doit fermer les
    DEUX apparitions, pas seulement la derniere."""
    events = common.pair_events([
        _rec(T, 1),
        _rec(T + 12 * MIN, 1),
        _rec(T + 80 * MIN, 4),
    ])
    apparitions = [e for e in events if e.type == 1]
    assert len(apparitions) == 2
    assert [e.appear_ts for e in apparitions] == [T, T + 12 * MIN]
    assert all(e.resolved_ts == T + 80 * MIN for e in apparitions)
    assert common.open_faults(events) == []


def test_trois_apparitions_une_resolution_ferme_les_trois():
    events = common.pair_events([
        _rec(T, 1),
        _rec(T + 12 * MIN, 1),
        _rec(T + 24 * MIN, 1),
        _rec(T + 80 * MIN, 4),
    ])
    assert len([e for e in events if e.type == 1]) == 3
    assert common.open_faults(events) == []


def test_apparitions_multiples_sans_resolution_restent_ouvertes():
    """Contrepartie : sans resolution, elles doivent bien rester ouvertes."""
    events = common.pair_events([_rec(T, 1), _rec(T + 12 * MIN, 1)])
    assert len(common.open_faults(events)) == 2


# ── Non-regression : ce qui marchait doit continuer ─────────────────────────

def test_appariement_simple_inchange():
    events = common.pair_events([_rec(T, 1), _rec(T + 30 * MIN, 4)])
    (e,) = events
    assert e.type == 1 and e.appear_ts == T and e.resolved_ts == T + 30 * MIN
    assert e.status == 0
    assert common.open_faults(events) == []


def test_resolution_orpheline_inchangee():
    """Resolution sans apparition dans la fenetre : evenement dedie, sans
    date d'apparition. C'est le cas des apparitions hors fenetre de scan."""
    (e,) = common.pair_events([_rec(T, 4)])
    assert e.type == 4
    assert e.appear_ts is None
    assert e.resolved_ts == T
    assert common.open_faults([e]) == []


def test_dedoublonnage_12s_inchange():
    """Retransmission firmware : une meme trame dans les 12 s est ignoree."""
    events = common.pair_events([_rec(T, 1), _rec(T + 5_000, 1)])
    assert len(events) == 1
    events = common.pair_events([
        _rec(T, 1), _rec(T + 30 * MIN, 4), _rec(T + 30 * MIN + 5_000, 4),
    ])
    assert len([e for e in events if e.resolved_ts is not None]) == 1


def test_cycles_apparies_inchanges():
    """Le defaut qui bat de l'aile : chaque apparition a sa propre resolution.
    Garde-fou contre une regression du cas normal, qui domine en volume —
    une pompe a produit une trentaine de ces cycles en vingt minutes."""
    records = []
    for i in range(10):
        base = T + i * 5 * MIN
        records.append(_rec(base, 1))
        records.append(_rec(base + 60_000, 4))
    events = common.pair_events(records)
    apparitions = [e for e in events if e.type == 1]
    assert len(apparitions) == 10
    assert all(e.resolved_ts == e.appear_ts + 60_000 for e in apparitions)
    assert common.open_faults(events) == []


def test_cles_distinctes_ne_se_melangent_pas():
    """Une resolution ne doit fermer que sa propre cle (defaut + sous-equipement)."""
    events = common.pair_events([
        _rec(T, 1, fault=88, dev=61),
        _rec(T, 1, fault=88, dev=62),
        _rec(T + 30 * MIN, 4, fault=88, dev=61),
    ])
    ouverts = common.open_faults(events)
    assert [(e.fault, e.device) for e in ouverts] == [(88, 62)]


def test_resolution_puis_reapparition_laisse_le_defaut_ouvert():
    """Ordre inverse : resolu puis reapparu. Le defaut est ouvert a la fin."""
    events = common.pair_events([
        _rec(T, 1), _rec(T + 20 * MIN, 4), _rec(T + 40 * MIN, 1),
    ])
    ouverts = common.open_faults(events)
    assert len(ouverts) == 1
    assert ouverts[0].appear_ts == T + 40 * MIN
