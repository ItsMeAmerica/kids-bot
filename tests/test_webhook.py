import hashlib
import hmac
import json
import threading
import urllib.request
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from kidsbot import brain, config, webhook
from kidsbot.brain import Brain, Decision
from kidsbot.server import PATH, make_server
from kidsbot.state import State

CFG = config.load(config.EXAMPLE_PATH)
PARENT, KID_A, KID_B = "+15550100000", "+15550100001", "+15550100002"
TZ = ZoneInfo("America/Denver")
NOON = datetime(2026, 10, 21, 12, 0, tzinfo=TZ)
LATE_NIGHT = datetime(2026, 10, 21, 22, 30, tzinfo=TZ)


class FakeTexts:
    def __init__(self, history=None):
        self.sent, self.history = [], history or []

    def send(self, to, text, key):
        self.sent.append((to, text, key))

    def recent(self, conversation_id, limit):
        return self.history[-limit:]


class FakeBrain:
    def __init__(self, decision=None):
        self.decision = decision or Decision("Try splitting 24 into 20 + 4. What do you get?")
        self.calls = []

    def decide(self, kid, history, text, now_text):
        self.calls.append((kid["name"], history, text))
        return self.decision


def event(phone, text, eid="evt_1", mid="m1", conv="c1"):
    return {
        "id": eid,
        "event_type": "imessage.received",
        "data": {"message": {"id": mid, "conversation_id": conv, "direction": "inbound",
                             "remote_number": phone, "is_group": False, "content": text}},
    }


def make(cfg=CFG, decision=None, history=None):
    texts, b = FakeTexts(history), FakeBrain(decision)
    return webhook.Handler(cfg, State(None), texts, b), texts, b


LIVE = {**CFG, "test_mode": False}


# --- signature ---

def sign(body, secret="whsec_abc", ts=1_700_000_000, rid="req_1"):
    sig = hmac.new(secret.removeprefix("whsec_").encode(), f"{rid}.{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Inkbox-Request-ID": rid, "X-Inkbox-Timestamp": str(ts), "X-Inkbox-Signature": f"sha256={sig}"}


def test_signature_checks():
    body = b'{"id":"evt_1"}'
    assert webhook.verify(body, sign(body), "whsec_abc", now=1_700_000_010)
    assert not webhook.verify(body + b" ", sign(body), "whsec_abc", now=1_700_000_010)  # body changed
    assert not webhook.verify(body, sign(body), "whsec_other", now=1_700_000_010)  # wrong key
    assert not webhook.verify(body, sign(body), "whsec_abc", now=1_700_000_000 + 301)  # too old
    assert not webhook.verify(body, {}, "whsec_abc", now=1_700_000_000)  # no headers


# --- kids ---

def test_kid_gets_answer_live():
    h, texts, b = make(LIVE)
    assert h.handle(event(KID_B, "what is 24 x 3"), now=NOON) == "answered"
    assert texts.sent == [(KID_B, "Try splitting 24 into 20 + 4. What do you get?", "evt_1:1")]
    assert b.calls[0][0] == "Kid B"


def test_test_mode_sends_kid_reply_to_parent_with_label():
    h, texts, _ = make()
    h.handle(event(KID_A, "hi"), now=NOON)
    assert texts.sent[0][:2] == (PARENT, "[Test for Kid A] Try splitting 24 into 20 + 4. What do you get?")


def test_same_event_twice_sends_once():
    h, texts, _ = make(LIVE)
    h.handle(event(KID_B, "hi"), now=NOON)
    assert h.handle(event(KID_B, "hi"), now=NOON) == "duplicate"
    assert len(texts.sent) == 1


def test_ignores_outbound_and_groups():
    h, texts, _ = make(LIVE)
    out = event(KID_B, "hi")
    out["data"]["message"]["direction"] = "outbound"
    assert h.handle(out, now=NOON) == "ignored"
    grp = event(KID_B, "hi", eid="evt_2")
    grp["data"]["message"]["is_group"] = True
    assert h.handle(grp, now=NOON) == "ignored group"
    assert texts.sent == []


def test_quiet_hours_canned_reply():
    h, texts, _ = make(LIVE)
    assert h.handle(event(KID_B, "help with math"), now=LATE_NIGHT) == "quiet"
    assert texts.sent[0][1] == webhook.LATE


def test_safety_alert_goes_out_even_in_quiet_hours():
    d = Decision("I'm really glad you told me. Please talk to a grown-up you trust.", True, "says kids at school are bullying them")
    h, texts, _ = make(LIVE, decision=d)
    assert h.handle(event(KID_B, "kids keep picking on me"), now=LATE_NIGHT) == "alert"
    to = [t[0] for t in texts.sent]
    assert to == [PARENT, KID_B]
    assert "bullying" in texts.sent[0][1] and texts.sent[1][1] == d.reply


def test_done_replies_nice_work_without_claude():
    h, texts, b = make(LIVE)
    assert h.handle(event(KID_B, "Done dishes"), now=NOON) == "done"
    assert texts.sent[0][1] == webhook.DONE and b.calls == []
    assert h.state.data["done"][0]["kid"] == "Kid B"


def test_daily_cap_notes_once_then_goes_quiet():
    cfg = {**LIVE, "daily_message_cap": 1}
    h, texts, _ = make(cfg)
    h.handle(event(KID_B, "q1", eid="e1"), now=NOON)
    assert h.handle(event(KID_B, "q2", eid="e2"), now=NOON) == "over cap"
    assert h.handle(event(KID_B, "q3", eid="e3"), now=NOON) == "over cap"
    assert [t[1] for t in texts.sent] == [FakeBrain().decision.reply, webhook.OVER_CAP]


def test_unknown_number_warned_once_and_parent_alerted():
    h, texts, b = make(LIVE)
    assert h.handle(event("+19995550123", "hey", eid="e1"), now=NOON) == "unknown"
    assert h.handle(event("+19995550123", "hey?", eid="e2"), now=NOON) == "unknown again"
    assert [t[0] for t in texts.sent] == ["+19995550123", PARENT]
    assert b.calls == []


def test_history_skips_the_new_message():
    hist = [("m0", "inbound", "can you help with fractions"), ("r0", "outbound", "Sure! What's the problem?"),
            ("m1", "inbound", "1/2 + 1/3")]
    h, _, b = make(LIVE, history=hist)
    h.handle(event(KID_B, "1/2 + 1/3"), now=NOON)
    assert b.calls[0][1] == [("user", "can you help with fractions"), ("assistant", "Sure! What's the problem?")]


# --- parent ---

def test_parent_can_test_as_kid_with_its_own_history():
    hist = [("p0", "inbound", "as Kid A: what's 7x8"), ("r0", "outbound", "[Test for Kid A] What's 7x7?"),
            ("p1", "inbound", "status"), ("r1", "outbound", "Bot is on"), ("m1", "inbound", "as kid a: 49")]
    h, texts, b = make(history=hist)
    assert h.handle(event(PARENT, "as kid a: 49"), now=NOON) == "answered"
    assert b.calls[0][:2] == ("Kid A", [("user", "what's 7x8"), ("assistant", "What's 7x7?")])
    assert b.calls[0][2] == "49"
    assert texts.sent[0][1].startswith("[Test for Kid A] ")


def test_parent_pause_and_resume():
    h, texts, b = make(LIVE)
    h.handle(event(PARENT, "pause Kid B", eid="e1"), now=NOON)
    assert h.handle(event(KID_B, "hi", eid="e2"), now=NOON) == "paused"
    h.handle(event(PARENT, "resume kid b", eid="e3"), now=NOON)
    assert h.handle(event(KID_B, "hi", eid="e4"), now=NOON) == "answered"
    assert texts.sent[1] == (KID_B, webhook.PAUSED, "e2:1")


def test_parent_other_text_gets_help():
    h, texts, _ = make()
    h.handle(event(PARENT, "hello?"), now=NOON)
    assert texts.sent[0][1] == webhook.PARENT_HELP


# --- Claude call ---

def test_brain_builds_request_and_reads_json():
    reply = {"reply": "What have you tried?", "alert_parent": False, "alert_reason": ""}
    resp = SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(reply))])
    calls = []
    client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: calls.append(kw) or resp))
    d = Brain(client, model="test-model").decide({"name": "Kid A", "age": 12}, [("assistant", "Morning!")], "help", "Wed noon")
    assert d == Decision("What have you tried?", False, "")
    kw = calls[0]
    assert kw["model"] == "test-model"
    assert kw["messages"] == [{"role": "user", "content": "help"}]  # can't start with the bot
    assert "Kid A, age band 9-12" in kw["system"] and "Tutor, don't solve" in kw["system"]
    assert kw["output_config"]["format"]["schema"] == brain.SCHEMA


def test_brain_falls_back_on_error():
    def boom(**kw):
        raise RuntimeError("down")
    client = SimpleNamespace(messages=SimpleNamespace(create=boom))
    assert Brain(client, model="m").decide({"name": "Kid A"}, [], "hi", "now").reply == brain.FALLBACK


def test_to_messages_merges_same_side():
    msgs = brain.to_messages([("user", "a"), ("user", "b"), ("assistant", "c")], "d")
    assert msgs == [{"role": "user", "content": "a\nb"}, {"role": "assistant", "content": "c"},
                    {"role": "user", "content": "d"}]


# --- HTTP server ---

@pytest.fixture
def server():
    h, texts, _ = make(LIVE)
    srv = make_server(h, "whsec_abc", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", texts
    srv.shutdown()


def post(url, body, headers):
    req = urllib.request.Request(url + PATH, data=body, headers=headers, method="POST")
    try:
        return urllib.request.urlopen(req).status
    except urllib.error.HTTPError as e:
        return e.code


def test_server_rejects_unsigned_and_accepts_signed(server, monkeypatch):
    url, texts = server
    body = json.dumps(event(KID_B, "hi")).encode()
    assert post(url, body, {}) == 401
    import time
    ts = int(time.time())
    assert post(url, body, sign(body, ts=ts)) == 200
    for _ in range(100):
        if texts.sent:
            break
        time.sleep(0.02)
    assert texts.sent and texts.sent[0][0] == KID_B
