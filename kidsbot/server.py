"""Always-on webhook server: Inkbox calls it the moment a text arrives.

Run with `python -m kidsbot.server`. Settings come from environment variables;
see README "Instant replies".
"""
from __future__ import annotations

import json
import os
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .brain import Brain
from .state import State
from .webhook import Handler, verify

PATH = "/webhooks/inkbox"


class InkboxTexts:
    """Sends and reads iMessages through the Inkbox identity."""

    def __init__(self, handle: str):
        from inkbox import Inkbox

        self.identity = Inkbox(api_key=os.environ["INKBOX_API_KEY"]).get_identity(handle)

    def send(self, to: str, text: str, key: str) -> None:
        self.identity.send_imessage(to=to, text=text, idempotency_key=key)

    def recent(self, conversation_id: str, limit: int) -> list[tuple[str, str, str]]:
        msgs = self.identity.list_imessages(conversation_id=conversation_id, limit=limit)
        msgs = sorted(msgs, key=lambda m: m.created_at)  # API returns newest first
        return [(str(m.id), m.direction, m.content or "") for m in msgs]


def make_server(handler: Handler, secret: str, port: int) -> ThreadingHTTPServer:
    jobs: queue.Queue = queue.Queue()

    def worker() -> None:
        # One at a time, so two quick texts from the same kid are answered in order.
        while True:
            event = jobs.get()
            try:
                print(f"{event.get('id')}: {handler.handle(event)}", flush=True)
            except Exception as exc:
                print(f"{event.get('id')}: failed {exc!r}", flush=True)

    threading.Thread(target=worker, daemon=True).start()

    class Web(BaseHTTPRequestHandler):
        def do_GET(self):  # health check for the host
            self._reply(200, b"ok")

        def do_POST(self):
            if self.path != PATH:
                return self._reply(404, b"not found")
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if not verify(body, dict(self.headers), secret):
                return self._reply(401, b"bad signature")
            try:
                jobs.put(json.loads(body))
            except json.JSONDecodeError:
                return self._reply(400, b"bad json")
            self._reply(200, b"ok")  # answer Inkbox right away; the worker replies to the kid

        def _reply(self, code: int, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # keep message text out of logs
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Web)


def main() -> None:
    cfg = config.load()
    state = State(os.environ.get("KIDSBOT_STATE", "state/server.json"))
    texts = InkboxTexts(os.environ.get("INKBOX_HANDLE", "bigbrain"))
    handler = Handler(cfg, state, texts, Brain())
    port = int(os.environ.get("PORT", "8080"))
    server = make_server(handler, os.environ["INKBOX_SIGNING_KEY"], port)
    print(f"kids-bot listening on :{port}{PATH} ({'test mode' if cfg.get('test_mode') else 'live'})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
