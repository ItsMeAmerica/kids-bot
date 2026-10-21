"""Handle one Inkbox `imessage.received` webhook: who sent it, what to say back."""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from inkbox import verify_webhook

from . import rules
from .brain import Brain
from .state import State

MAX_SKEW_SECONDS = 300
UNKNOWN = "This number is for our family only."
LATE = "It's late, ask me in the morning!"
PAUSED = "I'm taking a break right now. Ask a parent if you need something."
OVER_CAP = "That's a lot of texts for today! Let's pick this up tomorrow."
DONE = "Nice work!"
PARENT_HELP = (
    "Commands: 'as <Kid>: <text>' to test as a kid, 'pause <Kid>', 'resume <Kid>', 'status'."
)


def verify(body: bytes, headers: dict, secret: str, now: float | None = None) -> bool:
    """Signature matches and the timestamp is within 5 minutes."""
    h = {k.lower(): v for k, v in headers.items()}
    try:
        skew = abs((now or time.time()) - int(h.get("x-inkbox-timestamp", "")))
    except ValueError:
        return False
    return skew <= MAX_SKEW_SECONDS and verify_webhook(payload=body, headers=h, secret=secret)


class Texts(Protocol):
    def send(self, to: str, text: str, key: str) -> None: ...

    def recent(self, conversation_id: str, limit: int) -> list[tuple[str, str, str]]:
        """(message id, direction, text), oldest first; direction is "inbound" or "outbound"."""
        ...


def _find_kid(cfg: dict, name: str) -> dict | None:
    return next((k for k in cfg["kids"] if k["name"].lower() == name.strip().lower()), None)


class Handler:
    def __init__(self, cfg: dict, state: State, texts: Texts, brain: Brain, history_limit: int = 12):
        self.cfg, self.state, self.texts, self.brain = cfg, state, texts, brain
        self.tz = ZoneInfo(cfg.get("timezone", "UTC"))
        self.history_limit = history_limit

    def handle(self, event: dict, now: datetime | None = None) -> str:
        """Process one webhook event. Returns a short note of what happened (for logs and tests)."""
        msg = (event.get("data") or {}).get("message") or {}
        if event.get("event_type") != "imessage.received" or msg.get("direction") != "inbound":
            return "ignored"
        if msg.get("is_group"):
            return "ignored group"
        if not self.state.first_time(event.get("id") or msg.get("id", "")):
            return "duplicate"
        now = now or datetime.now(self.tz)
        self.key = event.get("id") or msg["id"]
        self.sends = 0
        text = (msg.get("content") or "").strip()
        phone = msg.get("remote_number") or msg.get("sender_number") or ""
        who, person = rules.who_is_texting(self.cfg, phone)

        if who == "unknown":
            if self.state.warn_unknown_once(phone):
                self._send(phone, UNKNOWN)
                self._alert(f"Unknown number {phone} texted the bot: {text[:200]}")
                return "unknown"
            return "unknown again"
        if who == "parent":
            return self._parent(text, msg, now)
        history = self._history(msg)
        return self._kid(person, text, history, now)

    # --- kids ---

    def _kid(self, kid: dict, text: str, history: list[tuple[str, str]], now: datetime) -> str:
        name, day = kid["name"], now.date().isoformat()
        if self.state.is_paused(name):
            self._to_kid(kid, PAUSED, count=False)
            return "paused"
        if rules.over_daily_cap(self.cfg, self.state.sent_today(name, day)):
            if not self.state.cap_noted(name, day):
                self._to_kid(kid, OVER_CAP, count=False)
            return "over cap"
        if re.match(r"^done\b", text, re.IGNORECASE):
            self.state.log_done(name, now.isoformat(timespec="minutes"), text)
            self._to_kid(kid, DONE, now=now)
            return "done"

        decision = self.brain.decide(kid, history, text, now.strftime("%A %B %-d, %-I:%M %p"))
        if decision.alert_parent:
            reason = decision.alert_reason or "safety concern"
            self._alert(f"Heads up about {name}: {reason}. They texted: \"{text[:300]}\"")
        quiet = rules.in_quiet_hours(self.cfg, now)
        # Quiet hours get the canned line, unless this is a safety message that needs a real answer.
        self._to_kid(kid, LATE if quiet and not decision.alert_parent else decision.reply, now=now)
        return "alert" if decision.alert_parent else ("quiet" if quiet else "answered")

    def _to_kid(self, kid: dict, text: str, now: datetime | None = None, count: bool = True) -> None:
        phone, label = rules.recipient(self.cfg, kid)
        self._send(phone, label + text)
        if count and now:
            self.state.count_sent(kid["name"], now.date().isoformat())

    # --- parent ---

    def _parent(self, text: str, msg: dict, now: datetime) -> str:
        m = re.match(r"^as\s+([^:]+):\s*(.*)$", text, re.IGNORECASE | re.DOTALL)
        if m and (kid := _find_kid(self.cfg, m.group(1))):
            if not self.cfg.get("test_mode"):
                self._send(self.cfg["parent"]["phone"], "'as <Kid>:' only works in test mode.")
                return "parent"
            history = self._test_history(msg, kid)
            return self._kid(kid, m.group(2).strip(), history, now)
        m = re.match(r"^(pause|resume)\s+(.+)$", text, re.IGNORECASE)
        if m and (kid := _find_kid(self.cfg, m.group(2))):
            paused = m.group(1).lower() == "pause"
            self.state.set_paused(kid["name"], paused)
            self._send(self.cfg["parent"]["phone"], f"{kid['name']} is {'paused' if paused else 'back on'}.")
            return "parent"
        if text.lower() == "status":
            day = now.date().isoformat()
            lines = [
                f"{k['name']}: {self.state.sent_today(k['name'], day)} replies today"
                + (", paused" if self.state.is_paused(k["name"]) else "")
                for k in self.cfg["kids"]
            ]
            mode = "test mode" if self.cfg.get("test_mode") else "live"
            self._send(self.cfg["parent"]["phone"], f"Bot is on ({mode}). " + "; ".join(lines))
            return "parent"
        self._send(self.cfg["parent"]["phone"], PARENT_HELP)
        return "parent"

    # --- helpers ---

    def _alert(self, text: str) -> None:
        self._send(self.cfg["parent"]["phone"], text)

    def _send(self, to: str, text: str) -> None:
        self.sends += 1
        # Same key on a webhook retry means Inkbox won't send it twice.
        self.texts.send(to, text, f"{self.key}:{self.sends}")

    def _recent(self, msg: dict, limit: int) -> list[tuple[str, str]]:
        """Earlier messages in this conversation, without the one being answered."""
        if not msg.get("conversation_id"):
            return []
        recent = self.texts.recent(msg["conversation_id"], limit + 1)
        return [(d, t) for i, d, t in recent if str(i) != str(msg.get("id"))][-limit:]

    def _history(self, msg: dict) -> list[tuple[str, str]]:
        return [("user" if d == "inbound" else "assistant", t) for d, t in self._recent(msg, self.history_limit)]

    def _test_history(self, msg: dict, kid: dict) -> list[tuple[str, str]]:
        """In test mode the parent's thread mixes everything; keep only this kid's pretend chat."""
        ask = re.compile(rf"^as\s+{re.escape(kid['name'])}\s*:\s*", re.IGNORECASE)
        label = f"[Test for {kid['name']}] "
        out = []
        for d, t in self._recent(msg, self.history_limit * 3):
            if d == "inbound" and ask.match(t):
                out.append(("user", ask.sub("", t)))
            elif d == "outbound" and t.startswith(label):
                out.append(("assistant", t[len(label):]))
        return out[-self.history_limit:]
