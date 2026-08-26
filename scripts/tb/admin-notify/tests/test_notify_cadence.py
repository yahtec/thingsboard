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
    """Le cas du defaut de communication qui bat de l'aile, a cheval sur deux
    fenetres de scan : le run 1 voit l'apparition, le run 2 la resolution."""
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    sent = _run(cl, monkeypatch, NOW + 10 * MIN, [(NOW + 5 * MIN, 4, 5, 1)])
    assert sent == []
    assert cl.attrs[fn.NOTIFY_STATE_ATTR] == {}
    assert _run(cl, monkeypatch, NOW + GRACE + MIN) == []


def test_fault_appearing_and_resolving_in_one_window_is_never_registered(monkeypatch):
    """Le meme defaut transitoire, mais entierement contenu dans UNE fenetre
    de scan. `pair_events` complete alors l'evenement d'apparition en place :
    un seul evenement de type 1 portant deja `resolved_ts`, et aucune fenetre
    de temps ne s'applique a cet appariement. Il ne doit laisser aucune trace
    en memoire, sinon il partirait en mail une heure plus tard et sa
    resolution, passee derriere le curseur, ne l'effacerait jamais."""
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    sent = _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1),
                                       (NOW - 4 * MIN, 4, 5, 1)])
    assert sent == []
    assert cl.attrs[fn.NOTIFY_STATE_ATTR] == {}
    assert _run(cl, monkeypatch, NOW + GRACE + MIN) == []


def test_new_appearance_rearms_a_stuck_entry_instead_of_being_swallowed(monkeypatch):
    """Une entree dont la resolution n'a jamais ete observee ne doit pas avaler
    les apparitions suivantes du meme defaut : `fresh` exigeant `mails == 0`,
    elles ne seraient sinon JAMAIS notifiees. Le cooldown 6 h est ce qui borne
    le rearmement."""
    stuck = {"1|5": {"appear_ts": NOW - 12 * 3600_000, "mails": 1,
                     "last_mail_ts": NOW - 11 * 3600_000}}
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN,
                       fn.NOTIFY_STATE_ATTR: stuck,
                       "recent_fault_notifs": {"1|5": NOW - 12 * 3600_000}})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    entry = cl.attrs[fn.NOTIFY_STATE_ATTR]["1|5"]
    assert entry == {"appear_ts": NOW - 5 * MIN, "mails": 0, "last_mail_ts": 0}
    sent = _run(cl, monkeypatch, NOW + GRACE)
    assert [to for to, _s in sent] == [["gerant@example.com"]]


def test_cursor_still_advances_when_there_is_nothing_to_scan(monkeypatch):
    """Le chemin `cursor >= cutoff` est le seul ou le curseur n'avance pas de
    lui-meme : il doit quand meme etre persiste, sinon M18 ne tient que par
    inspection."""
    cl = Client(attrs={"last_notified_evt_ts": NOW})
    assert _run(cl, monkeypatch, NOW) == []
    assert cl.attrs["last_notified_evt_ts"] == NOW
    assert cl.attrs[fn.NOTIFY_STATE_ATTR] == {}


def test_cooldown_blocks_creating_a_new_entry(monkeypatch):
    """Anti-rebond 6 h : il filtre desormais la CREATION d'entree, pas l'envoi.
    On verifie aussi la consequence — aucun mail au run suivant le sursis —
    et pas seulement la memoire restee vide."""
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN,
                       "recent_fault_notifs": {"1|5": NOW - 60 * MIN}})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    assert cl.attrs[fn.NOTIFY_STATE_ATTR] == {}
    assert _run(cl, monkeypatch, NOW + GRACE + MIN) == []


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


# ── Rappels en escalade (spec §4.2) ─────────────────────────────────────────

H = 3600_000
STEPS = [24 * H, 72 * H, 168 * H]


def test_reminder_due_follows_the_escalation_ladder():
    assert fn.reminder_due({"mails": 1, "last_mail_ts": 0}, 24 * H - 1, STEPS) is False
    assert fn.reminder_due({"mails": 1, "last_mail_ts": 0}, 24 * H, STEPS) is True
    assert fn.reminder_due({"mails": 2, "last_mail_ts": 0}, 72 * H - 1, STEPS) is False
    assert fn.reminder_due({"mails": 2, "last_mail_ts": 0}, 72 * H, STEPS) is True
    assert fn.reminder_due({"mails": 3, "last_mail_ts": 0}, 168 * H, STEPS) is True


def test_reminder_due_stays_on_the_last_step_beyond_the_ladder():
    assert fn.reminder_due({"mails": 9, "last_mail_ts": 0}, 167 * H, STEPS) is False
    assert fn.reminder_due({"mails": 9, "last_mail_ts": 0}, 168 * H, STEPS) is True


def test_reminder_due_never_fires_before_the_first_mail():
    assert fn.reminder_due({"mails": 0, "last_mail_ts": 0}, 999 * H, STEPS) is False


def test_unresolved_fault_is_reminded_at_24h_then_72h(monkeypatch):
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    t1 = NOW + GRACE
    _run(cl, monkeypatch, t1)                                  # mail d'apparition
    assert _run(cl, monkeypatch, t1 + 23 * H) == []
    sent = _run(cl, monkeypatch, t1 + 24 * H)
    assert len(sent) == 1 and "toujours" in sent[0][1].lower()
    t2 = t1 + 24 * H
    assert _run(cl, monkeypatch, t2 + 71 * H) == []
    assert len(_run(cl, monkeypatch, t2 + 72 * H)) == 1


def test_resolution_stops_the_reminders(monkeypatch):
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    t1 = NOW + GRACE
    _run(cl, monkeypatch, t1)
    _run(cl, monkeypatch, t1 + MIN, [(t1, 4, 5, 1)])
    assert cl.attrs[fn.NOTIFY_STATE_ATTR] == {}
    assert _run(cl, monkeypatch, t1 + 48 * H) == []


def test_appearance_and_reminder_are_two_distinct_mails(monkeypatch):
    """Un defaut mur et un autre a relancer dans le meme run : deux mails,
    deux sujets differents."""
    cl = Client(attrs={"last_notified_evt_ts": NOW - 10 * MIN})
    _run(cl, monkeypatch, NOW, [(NOW - 5 * MIN, 1, 5, 1)])
    t1 = NOW + GRACE
    _run(cl, monkeypatch, t1)
    # un second defaut apparait 24 h plus tard, murit, et le premier est du
    t2 = t1 + 24 * H
    _run(cl, monkeypatch, t2 - 30 * MIN, [(t2 - 35 * MIN, 1, 7, 1)])
    # Le run final doit laisser au second defaut le temps de son sursis :
    # t2 + 30 min lui donne 65 min depuis son apparition (t2 - 35 min), et
    # 24 h 30 depuis le mail d'apparition du premier, donc son rappel est du.
    sent = _run(cl, monkeypatch, t2 + 30 * MIN)
    subjects = [s for _to, s in sent]
    assert len(subjects) == 2
    assert any("toujours" in s.lower() for s in subjects)
    assert any("toujours" not in s.lower() for s in subjects)


# ── Amorcage depuis la memoire du digest ────────────────────────────────────

def test_flip_key_inverts_the_digest_convention():
    assert fn._flip_key("15|50") == "50|15"
    assert fn._flip_key("nawak") is None
    assert fn._flip_key("a|b|c") is None


def test_seed_from_digest_on_first_run(monkeypatch):
    """Attribut absent : on reprend les defauts deja connus du digest avec
    mails=1, pour qu'un defaut en cours au deploiement soit relance a 24 h."""
    cl = Client(attrs={"last_notified_evt_ts": NOW - MIN,
                       "digest_open_faults": {"5|1": NOW - 5 * 24 * H}})
    sent = _run(cl, monkeypatch, NOW)
    assert sent == []                                          # pas de re-annonce
    entry = cl.attrs[fn.NOTIFY_STATE_ATTR]["1|5"]
    assert entry["mails"] == 1 and entry["last_mail_ts"] == NOW
    assert len(_run(cl, monkeypatch, NOW + 24 * H)) == 1        # relance a 24 h


def test_no_reseed_once_the_attribute_exists(monkeypatch):
    cl = Client(attrs={"last_notified_evt_ts": NOW - MIN,
                       "digest_open_faults": {"5|1": NOW - 5 * 24 * H},
                       fn.NOTIFY_STATE_ATTR: {}})
    _run(cl, monkeypatch, NOW)
    assert cl.attrs[fn.NOTIFY_STATE_ATTR] == {}


def test_seed_tolerates_a_missing_or_corrupt_digest_memory():
    assert fn._seed_from_digest(None, NOW) == {}
    assert fn._seed_from_digest("corrompu", NOW) == {}
    assert fn._seed_from_digest({"nawak": 1}, NOW) == {}
