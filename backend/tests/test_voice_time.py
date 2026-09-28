"""
Timezone handling — gap #10.

The bug being pinned down: "Friday at 3 PM" spoken in Asia/Karachi was
stored as 15:00 UTC, five hours late, with no error. These tests assert the
conversion goes the right way and that unparseable input degrades to None
instead of to a plausible wrong time.
"""
from datetime import datetime

from app import voice_time


def test_local_iso_is_interpreted_in_the_speakers_zone():
    resolved = voice_time.resolve_spoken_datetime("2026-09-18T15:00", "Asia/Karachi")
    # 15:00 PKT is 10:00 UTC, and the stored value is naive UTC.
    assert resolved == datetime(2026, 9, 18, 10, 0)
    assert resolved.tzinfo is None


def test_offset_aware_input_is_respected_not_reinterpreted():
    resolved = voice_time.resolve_spoken_datetime("2026-09-18T15:00:00+00:00", "Asia/Karachi")
    assert resolved == datetime(2026, 9, 18, 15, 0)


def test_bare_date_is_accepted():
    assert voice_time.resolve_spoken_datetime("2026-09-18", "UTC") == datetime(2026, 9, 18, 0, 0)


def test_garbage_returns_none_rather_than_guessing():
    assert voice_time.resolve_spoken_datetime("sometime next week", "UTC") is None
    assert voice_time.resolve_spoken_datetime("", "UTC") is None
    assert voice_time.resolve_spoken_datetime(None, "UTC") is None


def test_unknown_zone_falls_back_to_utc_without_raising():
    assert voice_time.resolve_spoken_datetime("2026-09-18T15:00", "Mars/Olympus") == datetime(2026, 9, 18, 15, 0)


def test_round_trip_display_shows_the_speakers_local_time():
    stored = voice_time.resolve_spoken_datetime("2026-09-18T15:00", "Asia/Karachi")
    assert "15:00" in voice_time.format_for_user(stored, "Asia/Karachi")


def test_client_timezone_beats_user_and_company():
    class Obj:
        timezone = "Europe/London"

    assert voice_time.company_timezone(user=Obj(), company=Obj(), client_timezone="Asia/Dubai") == "Asia/Dubai"
    assert voice_time.company_timezone(user=Obj(), company=None) == "Europe/London"
    assert voice_time.company_timezone(user=None, company=None) == "UTC"


def test_prompt_mentions_the_weekday_and_zone():
    text = voice_time.prompt_now("Asia/Karachi")
    assert "Asia/Karachi" in text and "Today is" in text
