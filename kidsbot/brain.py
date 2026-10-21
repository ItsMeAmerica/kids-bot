"""Ask Claude for a reply to a kid's text."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import rules

PERSONA = Path(__file__).resolve().parent.parent / "prompts" / "kid_persona.md"
DEFAULT_MODEL = "claude-opus-5-5"

SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "description": "The text message to send back to the kid."},
        "alert_parent": {"type": "boolean", "description": "True when the persona's Escalate rules apply."},
        "alert_reason": {"type": "string", "description": "One line for the parent when alert_parent is true, else empty."},
    },
    "required": ["reply", "alert_parent", "alert_reason"],
    "additionalProperties": False,
}

FALLBACK = "Sorry, I'm having trouble right now. Try again in a bit, or ask a grown-up."


@dataclass
class Decision:
    reply: str
    alert_parent: bool = False
    alert_reason: str = ""


def system_prompt(kid: dict, now_text: str) -> str:
    return (
        PERSONA.read_text()
        + "\n\n## This conversation\n"
        + f"- You are texting with {kid['name']}, age band {rules.age_band(kid.get('age'))}.\n"
        + f"- It is now {now_text}.\n"
        + "- This is a text message: plain text, no markdown, keep it short.\n"
        + "- You can't see the calendar from here. For schedule questions, say to check the morning text or ask a parent.\n"
    )


def to_messages(history: list[tuple[str, str]], text: str) -> list[dict]:
    """Turn (role, text) history, oldest first, plus the new text into API messages.

    Merges back-to-back turns from the same side and makes sure the list starts
    with the kid, as the API requires.
    """
    turns: list[dict] = []
    for role, body in history + [("user", text)]:
        if not body:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] += "\n" + body
        else:
            turns.append({"role": role, "content": body})
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return turns


class Brain:
    def __init__(self, client=None, model: str | None = None):
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.environ.get("KIDSBOT_MODEL", DEFAULT_MODEL)

    def decide(self, kid: dict, history: list[tuple[str, str]], text: str, now_text: str) -> Decision:
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt(kid, now_text),
                messages=to_messages(history, text),
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            )
        except Exception as exc:  # network or API trouble: answer kindly and tell the server log
            print(f"claude error: {exc!r}")
            return Decision(FALLBACK)
        if resp.stop_reason == "refusal":
            return Decision("Let's talk about something else. If something is wrong, tell a grown-up you trust.")
        body = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return Decision(FALLBACK)
        return Decision(data["reply"].strip() or FALLBACK, bool(data["alert_parent"]), data.get("alert_reason", ""))


class CliBrain:
    """Same job as Brain, but through the Claude Code app (`claude -p`) on this computer.

    Uses whatever Claude plan Claude Code is signed in with, so no API key or
    extra bill. Claude Code must be installed and signed in once (`claude`).
    """

    def __init__(self, run=None, command: str | None = None, model: str | None = None):
        import subprocess

        self.run = run or subprocess.run
        self.command = command or os.environ.get("KIDSBOT_CLAUDE", "claude")
        self.model = model or os.environ.get("KIDSBOT_MODEL")

    def decide(self, kid: dict, history: list[tuple[str, str]], text: str, now_text: str) -> Decision:
        chat = "\n".join(f"{'Kid' if role == 'user' else 'You'}: {body}" for role, body in history)
        prompt = (f"Earlier messages:\n{chat}\n\n" if chat else "") + f"New text from the kid:\n{text}\n\nWrite your reply."
        args = [self.command, "-p", prompt, "--system-prompt", system_prompt(kid, now_text),
                "--tools", "", "--strict-mcp-config", "--no-session-persistence",
                "--output-format", "json", "--json-schema", json.dumps(SCHEMA)]
        if self.model:
            args += ["--model", self.model]
        try:
            out = self.run(args, capture_output=True, text=True, timeout=120)
            data = json.loads(out.stdout)["structured_output"]
        except Exception as exc:  # not installed, signed out, timed out, or odd output
            print(f"claude cli error: {exc!r}")
            return Decision(FALLBACK)
        return Decision(data["reply"].strip() or FALLBACK, bool(data["alert_parent"]), data.get("alert_reason", ""))


def make_brain():
    """API key set: call the API. Otherwise: use Claude Code on this computer."""
    return Brain() if os.environ.get("ANTHROPIC_API_KEY") else CliBrain()
