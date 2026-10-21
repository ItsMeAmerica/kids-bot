"""One-time setup: tell Inkbox to send new iMessages to your server.

    INKBOX_API_KEY=... python scripts/register_webhook.py https://your-host.example.com

Prints the signing key once. Save it as INKBOX_SIGNING_KEY on the host.
"""
import os
import sys

from inkbox import Inkbox

if len(sys.argv) != 2 or not sys.argv[1].startswith("https://"):
    sys.exit("usage: register_webhook.py https://your-host")

inkbox = Inkbox(api_key=os.environ["INKBOX_API_KEY"])
identity = inkbox.get_identity(os.environ.get("INKBOX_HANDLE", "bigbrain"))
sub = inkbox.webhooks.subscriptions.create(
    agent_identity_id=identity.id,
    url=sys.argv[1].rstrip("/") + "/webhooks/inkbox",
    event_types=["imessage.received"],
)
print("Webhook registered.")
print("INKBOX_SIGNING_KEY =", getattr(sub, "signing_key", None) or sub)
