import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from kidsbot import brain, poll
from kidsbot.brain import CliBrain, Decision
from kidsbot.state import State
from kidsbot.webhook import Handler
from test_webhook import CFG, KID_B, FakeBrain, FakeTexts

T0 = datetime(2026, 10, 21, 18, 0, tzinfo=timezone.utc)
LIVE = {**CFG, "test_mode": False}


def imsg(i, text, minutes, direction="inbound", phone=KID_B):
    return SimpleNamespace(id=f"m{i}", conversation_id="c1", direction=direction, remote_number=phone,
                           sender_number=phone, is_group=False, content=text,
                           created_at=T0 + timedelta(minutes=minutes))


class FakeIdentity:
    def __init__(self, msgs):
        self.msgs = msgs

    def list_imessages(self, limit):
        return sorted(self.msgs, key=lambda m: m.created_at, reverse=True)[:limit]  # newest first, like Inkbox


def setup(msgs, since=T0):
    state = State(None)
    state.data["since"] = since.isoformat()
    texts = FakeTexts()
    return Handler(LIVE, state, texts, FakeBrain()), FakeIdentity(msgs), state, texts


def test_answers_only_new_incoming_texts_in_order():
    msgs = [imsg(0, "old", -5), imsg(1, "first", 1), imsg(2, "bot reply", 2, "outbound"), imsg(3, "second", 3)]
    h, ident, state, texts = setup(msgs)
    assert poll.check_once(h, ident, state) == 2
    assert [c[2] for c in h.brain.calls] == ["first", "second"]
    assert state.data["since"] == (T0 + timedelta(minutes=3)).isoformat()


def test_next_check_does_not_answer_again():
    h, ident, state, texts = setup([imsg(1, "hi", 1)])
    poll.check_once(h, ident, state)
    poll.check_once(h, ident, state)
    assert len(texts.sent) == 1


def test_cli_brain_runs_claude_code_and_reads_structured_output():
    seen = {}

    def run(args, **kw):
        seen["args"] = args
        out = {"type": "result", "structured_output": {"reply": "What's 7 x 4?", "alert_parent": False, "alert_reason": ""}}
        return SimpleNamespace(stdout=json.dumps(out), returncode=0)

    d = CliBrain(run=run).decide({"name": "Kid A", "age": 12}, [("user", "7x8?"), ("assistant", "Try 7x4 first")], "28", "now")
    assert d == Decision("What's 7 x 4?", False, "")
    args = seen["args"]
    assert args[:2] == ["claude", "-p"] and "Kid: 7x8?\nYou: Try 7x4 first" in args[2] and "28" in args[2]
    assert args[args.index("--tools") + 1] == ""  # no file or command access
    assert json.loads(args[args.index("--json-schema") + 1]) == brain.SCHEMA


def test_cli_brain_falls_back_when_claude_code_missing():
    def run(args, **kw):
        raise FileNotFoundError("claude")
    assert CliBrain(run=run).decide({"name": "Kid A"}, [], "hi", "now").reply == brain.FALLBACK


def test_make_brain_picks_api_only_with_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert isinstance(brain.make_brain(), CliBrain)
