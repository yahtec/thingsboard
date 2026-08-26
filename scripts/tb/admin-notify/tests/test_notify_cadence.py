"""Sursis avant le premier mail client (spec §4.2). La detection inscrit,
l'envoi est pilote par la memoire `notify_open_faults`."""
import common
import fault_notify as fn

MIN = 60_000
NOW = 1_700_000_000_000
GRACE = 60 * MIN


def _ts_payload(events):
    """events: iterable de (ts, evt_type, fault, device)."""
    keys = ["evt_type", "evt_fault", "evt_device", "evt_status",
            "evt_date", "evt_time", "evt_id", "fault_src"]
    payload = {k: [] for k in keys}
    for ts, typ, fault, device in events:
        payload["evt_type"].append({"ts": ts, "value": typ})
        payload["evt_fault"].append({"ts": ts, "value": fault})
        payload["evt_device"].append({"ts": ts, "value": device})
        payload["evt_status"].append({"ts": ts, "value": 1})
        payload["evt_date"].append({"ts": ts, "value": "10/07/2026"})
        payload["evt_time"].append({"ts": ts, "value": "12:00:00"})
        payload["evt_id"].append({"ts": ts, "value": 1})
        payload["fault_src"].append({"ts": ts, "value": 0})
    return payload


DEV = {"id": {"id": "dev-1"}, "name": "111"}


class Client:
    """TBClient reel dont les attributs et la telemetrie sont en memoire, de
    sorte qu'on puisse enchainer plusieurs runs et voir l'etat evoluer."""

    def __init__(self, recipients=("gerant@example.com",), attrs=None):
        self.c = common.TBClient(url="http://test", user="svc", password="x")
        self.attrs = dict(attrs or {})
        self.payload = {}
        self.c.get_server_attrs = lambda etype, eid, keys=None: dict(self.attrs)
        self.c.save_server_attrs = lambda etype, eid, kv: self.attrs.update(kv)
        self.c.get_recipients_for_device = lambda dev_id, users=None: list(recipients)
        self.c.get_timeseries = lambda *a, **k: self.payload


def _run(cl, monkeypatch, now_ms, events=()):
    """Un run de process_device. Retourne la liste des envois captures."""
    sent = []
    monkeypatch.setattr(fn, "send_mail",
                        lambda to, subject, html, text=None: sent.append((to, subject)))
    cl.payload = _ts_payload(events)
    fn.process_device(cl.c, DEV, now_ms, now_ms - MIN)
    return sent


def test_appearance_is_registered_but_not_mailed_within_grace(monkeypatch):
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    sent = _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    assert sent == []
    tracked = cl.attrs[fn.NOTIFY_STATE_ATTR]
    assert list(tracked) == ["1|5"]
    assert tracked["1|5"]["mails"] == 0


def test_mail_goes_out_once_grace_elapsed(monkeypatch):
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    sent = _run(cl, monkeypatch, NOW + GRACE)
    assert [to for to, _ in sent] == [["gerant@example.com"]]
    assert cl.attrs[fn.NOTIFY_STATE_ATTR]["1|5"]["mails"] == 1


def test_mail_is_not_sent_twice_for_the_same_appearance(monkeypatch):
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    _run(cl, monkeypatch, NOW + GRACE)
    assert _run(cl, monkeypatch, NOW + GRACE + MIN) == []


def test_transient_fault_resolved_within_grace_sends_nothing(monkeypatch):
    """Le cas du defaut de communication qui bat de l'aile."""
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    sent = _run(cl, monkeypatch, NOW + 10 * MIN, [(NOW + 5 * MIN, 4, 5, 1)])
    assert sent == []
    assert cl.attrs[fn.NOTIFY_STATE_ATTR] == {}
    assert _run(cl, monkeypatch, NOW + GRACE + MIN) == []


def test_cooldown_blocks_creating_a_new_entry(monkeypatch):
    """Anti-rebond 6 h : il filtre desormais la CREATION d'entree, pas l'envoi."""
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN,
                       "recent_fault_notifs": {"1|5": NOW - 60 * MIN}})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    assert cl.attrs[fn.NOTIFY_STATE_ATTR] == {}


def test_cursor_advances_even_with_nothing_to_send(monkeypatch):
    """M18 preserve : le curseur ne se fige jamais."""
    cl = Client(recipients=(), attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    assert cl.attrs["last_notified_evt_ts"] == NOW - 5 * MIN


def test_no_recipient_still_consumes_the_deadline(monkeypatch):
    """Sans destinataire l'echeance est notee comme consommee, sinon elle se
    redeclencherait a chaque run pour toujours."""
    cl = Client(recipients=(), attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    _run(cl, monkeypatch, NOW + GRACE)
    assert cl.attrs[fn.NOTIFY_STATE_ATTR]["1|5"]["mails"] == 1


def test_load_notify_state_is_defensive():
    assert fn._load_notify_state("corrompu") == {}
    assert fn._load_notify_state({"1|5": "pas un dict"}) == {}
    assert fn._load_notify_state({"1|5": {"mails": 1}}) == {}   # appear_ts manquant
    assert fn._load_notify_state({"1|5": {"appear_ts": "7"}}) == {
        "1|5": {"appear_ts": 7, "mails": 0, "last_mail_ts": 0}}
