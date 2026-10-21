"""Small JSON file that remembers what the server has already done.

Kept in state/ (git-ignored). Losing it is harmless: at worst a kid's daily
count restarts or a paused kid has to be paused again.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

MAX_SEEN = 1000


class State:
    def __init__(self, path: Path | str | None):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self.data = {"seen": [], "sent": {}, "cap_noted": {}, "paused": [], "warned_unknown": [], "done": []}
        if self.path and self.path.exists():
            self.data.update(json.loads(self.path.read_text()))

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        tmp.replace(self.path)

    def first_time(self, key: str) -> bool:
        """True the first time a key (event or message id) is seen, False on repeats."""
        with self._lock:
            if key in self.data["seen"]:
                return False
            self.data["seen"] = (self.data["seen"] + [key])[-MAX_SEEN:]
            self._save()
            return True

    def sent_today(self, kid: str, day: str) -> int:
        return self.data["sent"].get(day, {}).get(kid, 0)

    def count_sent(self, kid: str, day: str) -> None:
        with self._lock:
            # Keep only today's counts so the file stays small.
            today = self.data["sent"].get(day, {})
            today[kid] = today.get(kid, 0) + 1
            self.data["sent"] = {day: today}
            self._save()

    def cap_noted(self, kid: str, day: str) -> bool:
        """True if the over-cap note already went out today; marks it sent."""
        with self._lock:
            if self.data["cap_noted"].get(kid) == day:
                return True
            self.data["cap_noted"][kid] = day
            self._save()
            return False

    def is_paused(self, kid: str) -> bool:
        return kid in self.data["paused"]

    def set_paused(self, kid: str, paused: bool) -> None:
        with self._lock:
            names = [k for k in self.data["paused"] if k != kid]
            self.data["paused"] = names + [kid] if paused else names
            self._save()

    def warn_unknown_once(self, phone: str) -> bool:
        """True the first time an unknown number texts."""
        with self._lock:
            if phone in self.data["warned_unknown"]:
                return False
            self.data["warned_unknown"].append(phone)
            self._save()
            return True

    def log_done(self, kid: str, when: str, text: str) -> None:
        with self._lock:
            self.data["done"] = (self.data["done"] + [{"kid": kid, "at": when, "text": text}])[-200:]
            self._save()
