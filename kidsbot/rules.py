"""Exact rules the routines rely on, kept here so they can be tested."""
from __future__ import annotations

from datetime import datetime, time, timedelta

def _t(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def who_is_texting(cfg: dict, phone: str) -> tuple[str, dict | None]:
    """Return ("parent", parent), ("kid", kid) or ("unknown", None)."""
    if phone == cfg["parent"]["phone"]:
        return "parent", cfg["parent"]
    for kid in cfg["kids"]:
        if kid["phone"] == phone:
            return "kid", kid
    return "unknown", None


DEFAULT_BAND = "9-12"


def age_band(age: int | None) -> str:
    if age is None:
        return DEFAULT_BAND
    if age <= 8:
        return "5-8"
    if age <= 12:
        return "9-12"
    return "13-17"


def in_quiet_hours(cfg: dict, now: datetime) -> bool:
    start, end, t = _t(cfg["quiet_hours"]["start"]), _t(cfg["quiet_hours"]["end"]), now.time()
    if start <= end:
        return start <= t < end
    return t >= start or t < end  # window crosses midnight


def over_daily_cap(cfg: dict, sent_today: int) -> bool:
    return sent_today >= cfg["daily_message_cap"]


def _is_chore(cfg: dict, ev: dict) -> bool:
    return ev.get("summary", "").lower().startswith(cfg["calendar"]["chore_prefix"].lower())


def _for_kid(cfg: dict, kid: dict, title: str) -> bool:
    title = title.lower()
    tags = [t.lower() for t in cfg["calendar"]["everyone_tags"]]
    return kid["name"].lower() in title or any(tag in title for tag in tags)


def events_for_kid(cfg: dict, kid: dict, events: list[dict]) -> list[dict]:
    """Non-chore calendar events whose title names the kid or carries an everyone tag."""
    return [e for e in events if not _is_chore(cfg, e) and _for_kid(cfg, kid, e.get("summary", ""))]


def chores_for_kid(cfg: dict, kid: dict, events: list[dict]) -> list[dict]:
    """Calendar events titled "Chore: <Kid> - <task>" (or "Chore: [All] - <task>")."""
    return [e for e in events if _is_chore(cfg, e) and _for_kid(cfg, kid, e.get("summary", ""))]


def chore_name(cfg: dict, ev: dict) -> str:
    """'Chore: Kid B - Take out trash' -> 'Take out trash'."""
    rest = ev["summary"][len(cfg["calendar"]["chore_prefix"]):].strip()
    return rest.split(" - ", 1)[1].strip() if " - " in rest else rest


def chores_due(cfg: dict, kid: dict, events: list[dict], now: datetime, window_minutes: int = 60) -> list[dict]:
    """The kid's chore events that started in (now - window, now]."""
    since = now - timedelta(minutes=window_minutes)
    due = []
    for ev in chores_for_kid(cfg, kid, events):
        start = datetime.fromisoformat(ev["start"])
        if since < start <= now:
            due.append(ev)
    return due


def recipient(cfg: dict, kid: dict) -> tuple[str, str]:
    """Phone to send a kid's message to, and a label prefix. Test mode reroutes to the parent."""
    if cfg.get("test_mode"):
        return cfg["parent"]["phone"], f"[Test for {kid['name']}] "
    return kid["phone"], ""
