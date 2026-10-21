"""Load and check config/family.yaml."""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
PHONE = re.compile(r"^\+\d{11,15}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
EXAMPLE_PATH = CONFIG_DIR / "family.yaml"
LOCAL_PATH = CONFIG_DIR / "family.local.yaml"


def default_path() -> Path:
    """Real config (KIDSBOT_CONFIG or family.local.yaml) if present, else the example."""
    if os.environ.get("KIDSBOT_CONFIG"):
        return Path(os.environ["KIDSBOT_CONFIG"])
    return LOCAL_PATH if LOCAL_PATH.exists() else EXAMPLE_PATH


def load(path: Path | str | None = None) -> dict:
    """Load and check the config. KIDSBOT_CONFIG_YAML (the whole file as text) wins when
    no path is given, for hosts where setting an environment variable is easier than a file."""
    if path is None and os.environ.get("KIDSBOT_CONFIG_YAML"):
        cfg = yaml.safe_load(os.environ["KIDSBOT_CONFIG_YAML"])
    else:
        with open(path or default_path()) as f:
            cfg = yaml.safe_load(f)
    problems = validate(cfg)
    if problems:
        raise ValueError("family.yaml problems:\n- " + "\n- ".join(problems))
    return cfg


def validate(cfg: dict) -> list[str]:
    problems: list[str] = []
    phones = [cfg["parent"]["phone"]]
    for key in ("start", "end"):
        if not TIME.match(cfg["quiet_hours"][key]):
            problems.append(f"quiet_hours.{key} must be HH:MM")
    for kid in cfg.get("kids", []):
        name = kid.get("name", "?")
        phones.append(kid.get("phone", ""))
        if not PHONE.match(kid.get("phone", "")):
            problems.append(f"{name}: phone must look like +15551234567")
        age = kid.get("age")
        if age is not None and not 4 <= int(age) <= 17:
            problems.append(f"{name}: age must be 4 to 17, or left blank")
        if kid.get("channel") not in ("imessage", "sms"):
            problems.append(f"{name}: channel must be imessage or sms")
        for chore in kid.get("chores", []):
            if not set(chore["days"]) <= DAYS:
                problems.append(f"{name}/{chore['name']}: unknown day")
            if not TIME.match(chore["time"]):
                problems.append(f"{name}/{chore['name']}: time must be HH:MM")
    if not cfg.get("calendar", {}).get("ids"):
        problems.append("calendar.ids needs at least one calendar")
    if len(set(phones)) != len(phones):
        problems.append("phone numbers must be unique")
    return problems
