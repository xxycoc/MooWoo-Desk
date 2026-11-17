"""Exchange-local regular hours for the frozen November 2026 competition."""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
FINAL_DAY = date(2026, 11, 27)
TRADING_DAYS = frozenset(date(2026, 11, day) for day in (17, 18, 19, 20, 23, 24, 25, 27))
# Fri 14 Nov 2026 was a full NYSE session; it supplies the first window day's completed bars.
COMPLETED_BEFORE_WINDOW = frozenset({date(2026, 11, 14)})


def local_time(now):
    if isinstance(now, str):
        now = datetime.fromisoformat(now.replace("Z", "+00:00"))
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("calendar requires a timezone-aware timestamp")
    return now.astimezone(NEW_YORK)


def utc_stamp(now):
    return local_time(now).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def session_date(value):
    if isinstance(value, datetime):
        return local_time(value).date()
    return date.fromisoformat(value) if isinstance(value, str) else value


def is_trading_day(day):
    return session_date(day) in TRADING_DAYS


def previous_session(day):
    """Last completed regular session before day, from the frozen calendar only."""
    day = session_date(day)
    earlier = [d for d in TRADING_DAYS | COMPLETED_BEFORE_WINDOW if d < day]
    if not earlier:
        raise ValueError("no known session before " + day.isoformat())
    return max(earlier)


def session_open(day):
    day = session_date(day)
    return datetime.combine(day, time(9, 30), NEW_YORK) if is_trading_day(day) else None


def session_close(day):
    day = session_date(day)
    return datetime.combine(day, time(13 if day == FINAL_DAY else 16), NEW_YORK) if is_trading_day(day) else None


def is_regular_hours(now):
    now = local_time(now)
    return is_trading_day(now) and session_open(now) <= now < session_close(now)


def minutes_since_open(now):
    now = local_time(now)
    opened = session_open(now)
    return (now - opened).total_seconds() / 60 if opened else None


def is_final_day(now):
    return local_time(now).date() >= FINAL_DAY


def run_allowed(kind, now):
    """Audits get a 35-minute window starting ten minutes after actual close."""
    now = local_time(now)
    if kind == "audit":
        closed = session_close(now)
        return bool(closed and closed + timedelta(minutes=10) <= now < closed + timedelta(minutes=45))
    if kind not in ("morning", "watch"):
        raise ValueError("unknown run kind")
    return is_regular_hours(now)


def skip(log, now, kind):
    if run_allowed(kind, now):
        return None
    reason = f"calendar skip: {kind} outside its competition session window"
    log.append("reflection_note", dict(prompt="Market calendar", text=reason, skipped=True), ts=utc_stamp(now))
    return dict(skipped=True, reason=reason, orders=[])


def skip_first_minutes(log, now, minimum):
    elapsed = minutes_since_open(now)
    if elapsed is not None and elapsed < minimum:
        reason = "calendar skip: no orders in first five regular-market minutes"
        log.append("reflection_note", dict(prompt="Market calendar", text=reason, skipped=True), ts=utc_stamp(now))
        return dict(skipped=True, reason=reason, orders=[])
    return None
