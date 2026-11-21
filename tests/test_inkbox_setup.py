from types import SimpleNamespace

import pytest

from kidsbot import inkbox_setup


class FakeSubs:
    def __init__(self, existing=(), key="whsec_new"):
        self.existing, self.key, self.created = list(existing), key, []

    def list(self, agent_identity_id, url):
        return [s for s in self.existing if s.url == url]

    def create(self, agent_identity_id, url, event_types):
        self.created.append((agent_identity_id, url, event_types))
        return SimpleNamespace(signing_key=self.key)


def fake_inkbox(subs, host="bigbrain.tunnel.example"):
    rotated = []
    return SimpleNamespace(
        webhooks=SimpleNamespace(subscriptions=subs),
        tunnels=SimpleNamespace(get=lambda tid: SimpleNamespace(public_host=host)),
        signing_keys=SimpleNamespace(create_or_rotate=lambda h: rotated.append(h) or SimpleNamespace(signing_key="whsec_rot")),
        rotated=rotated,
    )


IDENTITY = SimpleNamespace(id="id1", agent_handle="bigbrain", tunnel=SimpleNamespace(id="t1"))


def test_tunnel_url_uses_identity_tunnel_host():
    assert inkbox_setup.tunnel_url(fake_inkbox(FakeSubs()), IDENTITY) == "https://bigbrain.tunnel.example"


def test_tunnel_url_without_tunnel_explains():
    with pytest.raises(SystemExit):
        inkbox_setup.tunnel_url(fake_inkbox(FakeSubs()), SimpleNamespace(tunnel=None))


def test_register_creates_once_and_returns_first_key():
    subs = FakeSubs()
    url, key, created = inkbox_setup.register(fake_inkbox(subs), IDENTITY, "https://h.example/")
    assert url == "https://h.example/webhooks/inkbox" and key == "whsec_new" and created
    assert subs.created == [("id1", url, ["imessage.received"])]


def test_register_reuses_existing_subscription():
    url = "https://h.example/webhooks/inkbox"
    subs = FakeSubs([SimpleNamespace(url=url, event_types=["imessage.received"])])
    ink = fake_inkbox(subs)
    assert inkbox_setup.register(ink, IDENTITY, "https://h.example") == (url, None, False)
    assert subs.created == [] and ink.rotated == []


def test_register_new_key_rotates():
    ink = fake_inkbox(FakeSubs(key=None))
    _, key, _ = inkbox_setup.register(ink, IDENTITY, "https://h.example", new_key=True)
    assert key == "whsec_rot" and ink.rotated == ["bigbrain"]


def test_brain_defaults_to_fast_model(monkeypatch):
    from kidsbot.brain import Brain

    monkeypatch.delenv("KIDSBOT_MODEL", raising=False)
    assert Brain(client=object()).model == "claude-haiku-5-5"
