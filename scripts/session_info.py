"""Print today's session facts from the frozen calendar. No network or broker calls."""

import argparse
from datetime import datetime, timezone
import json

import _common  # noqa: F401
from moowoo import calendar


def info(now):
    now = calendar.local_time(now)
    day = now.date()
    opened, closed = calendar.session_open(day), calendar.session_close(day)
    prior = calendar.previous_session(day)
    return dict(now=calendar.utc_stamp(now), sessionDate=day.isoformat(),
                tradingDay=calendar.is_trading_day(day), regularHours=calendar.is_regular_hours(now),
                open=opened and calendar.utc_stamp(opened), close=closed and calendar.utc_stamp(closed),
                minutesSinceOpen=calendar.minutes_since_open(now), finalDay=calendar.is_final_day(now),
                barsAsOf=prior.isoformat(),
                # News cutoffs for movers from the barsAsOf session: open for gaps, close for close moves.
                barsAsOfOpen=calendar.utc_stamp(calendar.session_open(prior)),
                barsAsOfClose=calendar.utc_stamp(calendar.session_close(prior)),
                auditBarsAsOf=day.isoformat() if closed and now >= closed else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", help="ISO timestamp with offset; defaults to the current time")
    args = parser.parse_args()
    print(json.dumps(info(args.now or datetime.now(timezone.utc))))


if __name__ == "__main__":
    main()
