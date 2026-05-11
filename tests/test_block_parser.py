"""Tests for app.services.block_parser.parse_block_args (pure function)."""
from __future__ import annotations

from datetime import date, timezone
from zoneinfo import ZoneInfo

from app.services.block_parser import parse_block_args


TODAY = date(2026, 5, 11)
TZ = "Europe/Moscow"


def test_parse_today_with_time_range_and_label():
    spec = parse_block_args("today 14:00-15:00 обед", today_local=TODAY, tz_name=TZ)
    assert spec is not None
    assert spec.label == "обед"
    moscow_start = spec.starts_at.astimezone(ZoneInfo(TZ))
    assert moscow_start.hour == 14
    assert moscow_start.date() == TODAY


def test_parse_tomorrow_with_time_range():
    spec = parse_block_args("tomorrow 09:00-10:00 встреча", today_local=TODAY, tz_name=TZ)
    assert spec is not None
    moscow_start = spec.starts_at.astimezone(ZoneInfo(TZ))
    assert moscow_start.date() == date(2026, 5, 12)


def test_parse_iso_date_with_time_range():
    spec = parse_block_args(
        "2026-05-20 12:00-13:30 врач", today_local=TODAY, tz_name=TZ
    )
    assert spec is not None
    moscow_start = spec.starts_at.astimezone(ZoneInfo(TZ))
    assert moscow_start.date() == date(2026, 5, 20)
    moscow_end = spec.ends_at.astimezone(ZoneInfo(TZ))
    assert moscow_end.hour == 13 and moscow_end.minute == 30


def test_parse_multi_day_range():
    """date + date → all-day range, ends at start of day AFTER second date."""
    spec = parse_block_args(
        "2026-06-20 2026-06-25 каникулы", today_local=TODAY, tz_name=TZ
    )
    assert spec is not None
    assert spec.label == "каникулы"
    moscow_start = spec.starts_at.astimezone(ZoneInfo(TZ))
    moscow_end = spec.ends_at.astimezone(ZoneInfo(TZ))
    assert moscow_start.date() == date(2026, 6, 20)
    # June 25 fully included → end is June 26 00:00
    assert moscow_end.date() == date(2026, 6, 26)


def test_parse_empty_returns_none():
    assert parse_block_args("", today_local=TODAY, tz_name=TZ) is None


def test_parse_one_token_returns_none():
    assert parse_block_args("today", today_local=TODAY, tz_name=TZ) is None


def test_parse_invalid_date_returns_none():
    assert parse_block_args("2026-13-99 14:00-15:00 x", today_local=TODAY, tz_name=TZ) is None


def test_parse_end_before_start_returns_none():
    assert (
        parse_block_args("today 15:00-14:00 wat", today_local=TODAY, tz_name=TZ) is None
    )


def test_parse_multi_day_reverse_order_returns_none():
    assert (
        parse_block_args(
            "2026-06-25 2026-06-20 oops", today_local=TODAY, tz_name=TZ
        )
        is None
    )


def test_parse_no_label():
    spec = parse_block_args("today 14:00-15:00", today_local=TODAY, tz_name=TZ)
    assert spec is not None
    assert spec.label is None
