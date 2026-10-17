from datetime import datetime

from kidsbot import config, rules

CFG = config.load(config.EXAMPLE_PATH)
KID_A, KID_B = CFG["kids"]

EVENTS = [
    {"summary": "Kid B soccer practice", "start": "2026-10-19T16:30:00"},
    {"summary": "[All] Grandma visits", "start": "2026-10-19T18:00:00"},
    {"summary": "Kid A dentist", "start": "2026-10-19T10:00:00"},
    {"summary": "Chore: Kid B - Take out trash", "start": "2026-10-19T18:30:00"},
    {"summary": "Chore: [All] - Clean your room", "start": "2026-10-19T07:15:00"},
]


def test_config_is_valid():
    assert config.validate(CFG) == []
    assert CFG["timezone"] == "America/Denver"


def test_who_is_texting():
    assert rules.who_is_texting(CFG, "+15550100002") == ("kid", KID_B)
    assert rules.who_is_texting(CFG, "+15550100001") == ("kid", KID_A)
    assert rules.who_is_texting(CFG, "+15550100000")[0] == "parent"
    assert rules.who_is_texting(CFG, "+19999999999") == ("unknown", None)


def test_age_band():
    assert rules.age_band(None) == "9-12"
    assert rules.age_band(6) == "5-8"
    assert rules.age_band(13) == "13-17"


def test_quiet_hours_cross_midnight():
    assert rules.in_quiet_hours(CFG, datetime(2026, 10, 19, 22, 0))
    assert rules.in_quiet_hours(CFG, datetime(2026, 10, 19, 6, 59))
    assert not rules.in_quiet_hours(CFG, datetime(2026, 10, 19, 7, 0))


def test_events_for_kid_skip_chores():
    kept = [e["summary"] for e in rules.events_for_kid(CFG, KID_B, EVENTS)]
    assert kept == ["Kid B soccer practice", "[All] Grandma visits"]


def test_chores_for_kid():
    b = [rules.chore_name(CFG, e) for e in rules.chores_for_kid(CFG, KID_B, EVENTS)]
    assert b == ["Take out trash", "Clean your room"]
    a = [rules.chore_name(CFG, e) for e in rules.chores_for_kid(CFG, KID_A, EVENTS)]
    assert a == ["Clean your room"]


def test_chores_due_window():
    due = rules.chores_due(CFG, KID_B, EVENTS, datetime(2026, 10, 19, 18, 30))
    assert [rules.chore_name(CFG, e) for e in due] == ["Take out trash"]
    assert rules.chores_due(CFG, KID_B, EVENTS, datetime(2026, 10, 19, 19, 31)) == []


def test_bad_config_is_caught():
    bad = {**CFG, "kids": [{**KID_B, "phone": "555", "age": 30, "channel": "fax"}]}
    assert len(config.validate(bad)) == 3


def test_test_mode_reroutes_to_parent():
    assert rules.recipient(CFG, KID_B) == ("+15550100000", "[Test for Kid B] ")
    live = {**CFG, "test_mode": False}
    assert rules.recipient(live, KID_B) == ("+15550100002", "")
