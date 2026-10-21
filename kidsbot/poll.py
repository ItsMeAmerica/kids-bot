"""Run the bot on your own computer: check Inkbox for new texts every few seconds.

No host, no public web address, no signing key. Replies come from Claude Code
on this computer (or the API if ANTHROPIC_API_KEY is set). It only works while
the computer is on and awake. Run with `python -m kidsbot.poll`.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from . import config
from .brain import make_brain
from .server import InkboxTexts
from .state import State
from .webhook import Handler


def as_event(m) -> dict:
    """Shape an Inkbox IMessage like the webhook payload, so one handler serves both."""
    return {
        "id": f"msg_{m.id}",
        "event_type": "imessage.received",
        "data": {"message": {
            "id": str(m.id), "conversation_id": str(m.conversation_id), "direction": m.direction,
            "remote_number": m.remote_number, "sender_number": m.sender_number,
            "is_group": m.is_group, "content": m.content,
        }},
    }


def new_texts(identity, since: datetime, limit: int = 30) -> list:
    """Incoming one-to-one texts from `since` on, oldest first. Ones already answered
    are skipped by the handler, so a text at exactly `since` is never lost or doubled."""
    msgs = identity.list_imessages(limit=limit)
    return sorted((m for m in msgs if m.direction == "inbound" and m.created_at >= since),
                  key=lambda m: m.created_at)


def check_once(handler: Handler, identity, state: State) -> int:
    since = datetime.fromisoformat(state.data["since"])
    found = new_texts(identity, since)
    for m in found:
        result = handler.handle(as_event(m))
        if result != "duplicate":
            print(f"{m.id}: {result}", flush=True)
        state.data["since"] = m.created_at.isoformat()
    if found:
        state.save()
    return len(found)


def main() -> None:
    cfg = config.load()
    state = State(os.environ.get("KIDSBOT_STATE", "state/server.json"))
    # First run: start from now, so old texts don't all get answered at once.
    state.data.setdefault("since", datetime.now(timezone.utc).isoformat())
    state.save()
    texts = InkboxTexts(os.environ.get("INKBOX_HANDLE", "bigbrain"))
    handler = Handler(cfg, state, texts, make_brain())
    every = float(os.environ.get("KIDSBOT_POLL_SECONDS", "15"))
    print(f"kids-bot checking for texts every {every:g}s ({'test mode' if cfg.get('test_mode') else 'live'}). Ctrl+C stops it.", flush=True)
    while True:
        try:
            check_once(handler, texts.identity, state)
        except Exception as exc:  # network blip: try again next round
            print(f"check failed: {exc!r}", flush=True)
        time.sleep(every)


if __name__ == "__main__":
    main()
