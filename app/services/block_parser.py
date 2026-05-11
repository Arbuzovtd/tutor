"""Pure parser for the /block command.

Accepted formats (token-separated):
    /block today 14:00-15:00 обед
    /block tomorrow 14:00-15:00 ремонт
    /block 2026-05-15 14:00-15:00 что-то
    /block 2026-05-15 2026-05-20 каникулы   (multi-day, all-day)

Returns a BlockSpec with starts_at and ends_at already in UTC, plus an optional
label. None on malformed input.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class BlockSpec:
    starts_at: datetime  # UTC
    ends_at: datetime  # UTC
    label: str | None


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RANGE_RE = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


def _resolve_date(token: str, *, today_local: date) -> date | None:
    if token == "today":
        return today_local
    if token == "tomorrow":
        return today_local + timedelta(days=1)
    if _DATE_RE.match(token):
        try:
            return date.fromisoformat(token)
        except ValueError:
            return None
    return None


def parse_block_args(args: str, *, today_local: date, tz_name: str) -> BlockSpec | None:
    """Parse the arguments portion (everything after '/block ')."""
    tz = ZoneInfo(tz_name)
    tokens = args.strip().split(maxsplit=2)
    if len(tokens) < 2:
        return None

    first = _resolve_date(tokens[0], today_local=today_local)
    if first is None:
        return None

    # Form 1: date + time range + label
    m = _TIME_RANGE_RE.match(tokens[1])
    if m is not None:
        sh, sm, eh, em = (int(x) for x in m.groups())
        try:
            start_local = datetime.combine(first, time(sh, sm), tzinfo=tz)
            end_local = datetime.combine(first, time(eh, em), tzinfo=tz)
        except ValueError:
            return None
        if end_local <= start_local:
            return None
        label = tokens[2].strip() if len(tokens) == 3 else None
        return BlockSpec(
            starts_at=start_local.astimezone(ZoneInfo("UTC")),
            ends_at=end_local.astimezone(ZoneInfo("UTC")),
            label=label,
        )

    # Form 2: date + date + label (all-day multi-day block)
    second = _resolve_date(tokens[1], today_local=today_local)
    if second is None or second < first:
        return None
    start_local = datetime.combine(first, time.min, tzinfo=tz)
    # end at the start of the day AFTER `second`, so the whole `second` is included
    end_local = datetime.combine(second + timedelta(days=1), time.min, tzinfo=tz)
    label = tokens[2].strip() if len(tokens) == 3 else None
    return BlockSpec(
        starts_at=start_local.astimezone(ZoneInfo("UTC")),
        ends_at=end_local.astimezone(ZoneInfo("UTC")),
        label=label,
    )
