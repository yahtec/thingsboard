"""M18 : un device sans destinataires doit quand meme avancer son curseur,
sinon jusqu'a 24h de vieux defauts partent en rafale au 1er CanView accorde."""
import common
import fault_notify as fn

NOW = 1_700_000_000_000
CURSOR = NOW - 500_000
CUTOFF = NOW - 60_000
APPEAR_TS = NOW - 400_000

DEV = {"id": {"id": "dev-1"}, "name": "Chaufferie Test"}


def _ts_payload():
    return {
        "evt_type": [{"ts": APPEAR_TS, "value": 1}],
        "evt_fault": [{"ts": APPEAR_TS, "value": 5}],
        "evt_device": [{"ts": APPEAR_TS, "value": 1}],
        "evt_status": [{"ts": APPEAR_TS, "value": 1}],
        "evt_date": [{"ts": APPEAR_TS, "value": "10/07/2026"}],
        "evt_time": [{"ts": APPEAR_TS, "value": "12:00:00"}],
        "evt_id": [{"ts": APPEAR_TS, "value": 1}],
        "fault_src": [{"ts": APPEAR_TS, "value": 0}],
    }


def make_client(recipients):
    c = common.TBClient(url="http://test", user="svc", password="x")
    c.get_server_attrs = lambda etype, eid, keys=None: {"last_notified_evt_ts": CURSOR}
    c.get_recipients_for_device = lambda dev_id, users=None: list(recipients)
    c.get_timeseries = lambda *a, **k: _ts_payload()
    saved = {}
    c.save_server_attrs = lambda etype, eid, kv: saved.update(kv)
    c.calls = {"save_server_attrs": saved}
    return c


def test_no_recipients_still_advances_cursor(monkeypatch):
    c = make_client([])
    sent = []
    monkeypatch.setattr(fn, "send_mail", lambda *a, **k: sent.append(a))

    fn.process_device(c, DEV, NOW, CUTOFF)

    assert sent == []  # pas de destinataire -> pas de mail
    # Le curseur doit avancer jusqu'au dernier ts scanne, pas rester bloque.
    assert c.calls["save_server_attrs"].get("last_notified_evt_ts") == APPEAR_TS


def test_with_recipients_sends_after_grace_and_advances(monkeypatch):
    """Le mail part au run qui suit l'ecoulement du sursis, pas a la
    detection. Le curseur, lui, avance des le premier run."""
    c = make_client(["syndic@ex.com"])
    sent = []
    monkeypatch.setattr(fn, "send_mail", lambda to, subject, html, text=None: sent.append(to))

    fn.process_device(c, DEV, NOW, CUTOFF)
    assert sent == []                                     # sursis en cours
    assert c.calls["save_server_attrs"].get("last_notified_evt_ts") == APPEAR_TS

    later = APPEAR_TS + 61 * 60_000
    c.get_server_attrs = lambda etype, eid, keys=None: dict(c.calls["save_server_attrs"])
    c.get_timeseries = lambda *a, **k: {}
    fn.process_device(c, DEV, later, later - 60_000)
    assert sent == [["syndic@ex.com"]]
