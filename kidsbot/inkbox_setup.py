"""One-time Inkbox setup for the home server: find the public web address and
tell Inkbox to send new iMessages there.

    python -m kidsbot.inkbox_setup                 # use the identity's built-in Inkbox tunnel
    python -m kidsbot.inkbox_setup https://host    # or your own public address

Needs INKBOX_API_KEY. Prints INKBOX_SIGNING_KEY once if Inkbox makes a new one.
Safe to run again: an existing subscription for the same address is reused.
"""
from __future__ import annotations

import argparse
import os
import sys

from .server import PATH

EVENTS = ["imessage.received"]


def tunnel_url(inkbox, identity) -> str:
    """https://<host> of the identity's Inkbox tunnel, which forwards to this computer
    while `python -m kidsbot.server` runs with KIDSBOT_TUNNEL=1."""
    if not identity.tunnel:
        raise SystemExit("This Inkbox identity has no tunnel. Pass your own https:// address instead.")
    return "https://" + inkbox.tunnels.get(identity.tunnel.id).public_host


def register(inkbox, identity, base_url: str, new_key: bool = False) -> tuple[str, str | None, bool]:
    """Subscribe the identity's iMessages to base_url + PATH.

    Returns (webhook url, signing key or None, created). The signing key is only
    known when Inkbox makes one: on the identity's first subscription, or when
    new_key asks for a fresh one (which replaces the old key for every webhook
    on this identity).
    """
    url = base_url.rstrip("/") + PATH
    existing = [s for s in inkbox.webhooks.subscriptions.list(agent_identity_id=identity.id, url=url)
                if set(EVENTS) <= set(s.event_types)]
    key = None
    created = not existing
    if created:
        sub = inkbox.webhooks.subscriptions.create(agent_identity_id=identity.id, url=url, event_types=EVENTS)
        key = getattr(sub, "signing_key", None)
    if new_key:
        key = inkbox.signing_keys.create_or_rotate(identity.agent_handle).signing_key
    return url, key, created


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url", nargs="?", help="your own public https:// address (default: the Inkbox tunnel)")
    ap.add_argument("--new-signing-key", action="store_true",
                    help="make a fresh signing key (replaces the old one for all of this identity's webhooks)")
    args = ap.parse_args(argv)
    if args.url and not args.url.startswith("https://"):
        sys.exit("The address must start with https://")

    from inkbox import Inkbox

    inkbox = Inkbox(api_key=os.environ["INKBOX_API_KEY"])
    identity = inkbox.get_identity(os.environ.get("INKBOX_HANDLE", "bigbrain"))
    base = args.url or tunnel_url(inkbox, identity)
    url, key, created = register(inkbox, identity, base, args.new_signing_key)
    print(("Webhook registered: " if created else "Webhook already registered: ") + url)
    if key:
        print(f"\nPut this line in your .env file (shown only once):\nINKBOX_SIGNING_KEY={key}")
    elif created or not os.environ.get("INKBOX_SIGNING_KEY"):
        print("\nThis identity already had a signing key, so Inkbox didn't show it again. If you don't "
              "have it, run again with --new-signing-key.")


if __name__ == "__main__":
    main()
